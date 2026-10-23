use anyhow::{Context, Result, ensure};
use async_trait::async_trait;
use glob::Pattern;
use reqwest::{Client, StatusCode, header, redirect::Policy};
use serde::{Deserialize, Serialize};
use spider::{
    fetcher::{FetchContext, RemoteFetcher},
    utils::PageResponse,
    website::Website,
};
use std::collections::HashSet;
use std::fs::OpenOptions;
use std::io::{BufWriter, Write};
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::time::{Instant, sleep_until};
use url::Url;

use crate::extract::{ExtractConfig, Extractor};
use crate::links::normalize_url;

#[derive(Debug, Deserialize)]
pub struct CrawlPlan {
    pub seed_urls: Vec<String>,
    pub scope_prefix: String,
    pub document_url_patterns: Vec<String>,
    pub selectors: ExtractConfig,
    pub max_pages: usize,
}

#[derive(Debug, Default, Serialize)]
pub struct CrawlReport {
    /// Page HTTP attempts, including redirect hops; excludes the robots.txt lookup.
    pub attempted: usize,
    pub succeeded: usize,
    pub skipped: usize,
    pub limit_reached: bool,
    pub failures: Vec<CrawlFailure>,
}

#[derive(Debug, Serialize)]
pub struct CrawlFailure {
    pub url: String,
    pub error: String,
}

struct State {
    report: CrawlReport,
    requested: HashSet<String>,
    writer: BufWriter<std::fs::File>,
    extractor: Extractor,
    patterns: Vec<Pattern>,
    write_error: Option<anyhow::Error>,
}

impl State {
    fn save(&mut self, response: &PageResponse) -> Result<()> {
        let url = response.final_url.as_deref().context("missing final URL")?;
        let path = Url::parse(url)?;
        if !self
            .patterns
            .iter()
            .any(|pattern| pattern.matches(path.path()))
        {
            self.report.skipped += 1;
            return Ok(());
        }
        let html = String::from_utf8_lossy(response.content.as_deref().unwrap_or_default());
        match self.extractor.extract_document(&html, url) {
            Ok(document) if !document.title.trim().is_empty() => {
                serde_json::to_writer(&mut self.writer, &document)?;
                self.writer.write_all(b"\n")?;
                self.report.succeeded += 1;
            }
            result => self.report.failures.push(CrawlFailure {
                url: url.to_owned(),
                error: match result {
                    Err(error) => error.to_string(),
                    Ok(_) => "extracted title is empty".to_owned(),
                },
            }),
        }
        Ok(())
    }
}

struct CrawlFetcher {
    client: Client,
    scope: Url,
    max_pages: usize,
    state: Arc<Mutex<State>>,
    next_request: tokio::sync::Mutex<Instant>,
}

fn in_scope(url: &Url, scope: &Url) -> bool {
    url.origin() == scope.origin() && url.path().starts_with(scope.path())
}

fn path_pattern(value: &str) -> Result<Pattern> {
    let mut value = value.to_owned();
    // fnmatch has no recursive ** operator and treats an unmatched [ literally.
    while value.contains("**") {
        value = value.replace("**", "*");
    }
    loop {
        match Pattern::new(&value) {
            Ok(pattern) => return Ok(pattern),
            Err(error) => {
                let (offset, character) = value
                    .char_indices()
                    .nth(error.pos)
                    .context("invalid glob")?;
                ensure!(character == '[', "invalid document URL glob: {error}");
                value.replace_range(offset..offset + 1, "[[]");
            }
        }
    }
}

impl CrawlFetcher {
    async fn download(&self, value: &str, delay: u64) -> Result<Option<PageResponse>> {
        let mut url = Url::parse(&normalize_url(value)?)?;
        for hop in 0..=5 {
            ensure!(
                in_scope(&url, &self.scope),
                "URL or redirect is outside crawl scope: {url}"
            );
            {
                let mut next = self.next_request.lock().await;
                sleep_until(*next).await;
                *next = Instant::now() + Duration::from_millis(delay.max(200));
            }
            {
                let mut state = self.state.lock().unwrap();
                if state.write_error.is_some() || state.requested.contains(url.as_str()) {
                    return Ok(None);
                }
                if state.report.attempted >= self.max_pages {
                    state.report.limit_reached = true;
                    return Ok(None);
                }
                state.requested.insert(url.to_string());
                state.report.attempted += 1;
            }
            let mut response = self.client.get(url.clone()).send().await?;
            if response.status().is_redirection() {
                ensure!(hop < 5, "too many redirects");
                let location = response
                    .headers()
                    .get(header::LOCATION)
                    .context("redirect has no Location header")?
                    .to_str()?;
                url = url.join(location)?;
                url.set_fragment(None);
                continue;
            }
            response.error_for_status_ref()?;
            let headers = response.headers().clone();
            let status_code = response.status();
            let content_type = headers
                .get(header::CONTENT_TYPE)
                .and_then(|value| value.to_str().ok())
                .unwrap_or("text/html");
            if !content_type.starts_with("text/html")
                && !content_type.starts_with("application/xhtml+xml")
            {
                self.state.lock().unwrap().report.skipped += 1;
                return Ok(None);
            }
            let mut content = Vec::new();
            while let Some(chunk) = response.chunk().await? {
                ensure!(
                    content.len() + chunk.len() <= 8 * 1024 * 1024,
                    "HTML exceeds 8 MiB"
                );
                content.extend_from_slice(&chunk);
            }
            return Ok(Some(PageResponse {
                content: Some(content),
                headers: Some(headers),
                status_code,
                final_url: Some(url.to_string()),
                ..Default::default()
            }));
        }
        unreachable!()
    }
}

#[async_trait]
impl RemoteFetcher for CrawlFetcher {
    async fn fetch(&self, ctx: FetchContext<'_>) -> PageResponse {
        match self.download(ctx.url, ctx.configuration.delay).await {
            Ok(Some(response)) => {
                let mut state = self.state.lock().unwrap();
                // Save before returning bytes to Spider: no lossy broadcast subscription.
                if let Err(error) = state.save(&response) {
                    state.write_error = Some(error);
                }
                response
            }
            Ok(None) => PageResponse {
                status_code: StatusCode::NO_CONTENT,
                ..Default::default()
            },
            Err(error) => {
                self.state
                    .lock()
                    .unwrap()
                    .report
                    .failures
                    .push(CrawlFailure {
                        url: ctx.url.to_owned(),
                        error: format!("{error:#}"),
                    });
                PageResponse {
                    status_code: StatusCode::BAD_GATEWAY,
                    ..Default::default()
                }
            }
        }
    }
}

/// Execute a plan using Spider for traversal and the existing extractor for documents.
pub async fn crawl(plan: &CrawlPlan, output: &Path) -> Result<CrawlReport> {
    ensure!(
        !plan.seed_urls.is_empty() && plan.max_pages > 0,
        "crawl needs seeds and a positive max_pages"
    );
    ensure!(
        !plan.document_url_patterns.is_empty(),
        "document URL patterns are empty"
    );
    let scope = Url::parse(&plan.scope_prefix).context("invalid scope_prefix")?;
    ensure!(
        matches!(scope.scheme(), "http" | "https")
            && scope.path().ends_with('/')
            && scope.query().is_none()
            && scope.fragment().is_none(),
        "scope_prefix must be an HTTP(S) directory URL ending in /"
    );
    let seeds: Vec<String> = plan
        .seed_urls
        .iter()
        .map(|url| {
            let url = normalize_url(url)?;
            ensure!(
                in_scope(&Url::parse(&url)?, &scope),
                "seed is outside crawl scope: {url}"
            );
            Ok(url)
        })
        .collect::<Result<_>>()?;
    let patterns = plan
        .document_url_patterns
        .iter()
        .map(|value| path_pattern(value))
        .collect::<Result<Vec<_>>>()?;
    let extractor = Extractor::new(&plan.selectors)?;
    let limit = u32::try_from(plan.max_pages)?
        .checked_add(1)
        .context("max_pages is too large")?;
    let file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(output)?;
    let state = Arc::new(Mutex::new(State {
        report: CrawlReport::default(),
        requested: HashSet::new(),
        writer: BufWriter::new(file),
        extractor,
        patterns,
        write_error: None,
    }));
    let client = Client::builder()
        .user_agent("mas-crawler/0.1")
        .timeout(Duration::from_secs(20))
        .redirect(Policy::none())
        .retry(reqwest::retry::never())
        .build()?;
    let mut site = Website::new(&seeds[0]);
    site.set_extra_links(seeds.iter().skip(1).cloned().map(Into::into).collect());
    site.with_whitelist_url(Some(vec![
        format!("^{}", regex::escape(scope.as_str())).into(),
    ]))
    .with_concurrency_limit(Some(8))
    .with_delay(200)
    .with_user_agent(Some("mas-crawler/0.1"))
    .with_respect_robots_txt(true);
    site.configuration.configure_allowlist();
    // Spider 2.53.9 decrements its remote-branch budget before admission.
    // The fetcher below enforces the actual page HTTP-attempt cap, including redirects.
    site.with_limit(limit);
    site.configure_robots_parser(&client).await;
    site.with_remote_fetcher(CrawlFetcher {
        client,
        scope,
        max_pages: plan.max_pages,
        state: Arc::clone(&state),
        next_request: tokio::sync::Mutex::new(Instant::now()),
    });
    // Keep extra seeds: Spider's fresh-run setup otherwise clears them.
    site.persist_links().crawl_raw().await;
    let mut state = state.lock().unwrap();
    if let Some(error) = state.write_error.take() {
        return Err(error);
    }
    state.writer.flush()?;
    state.report.limit_reached |= state.report.attempted >= plan.max_pages;
    Ok(std::mem::take(&mut state.report))
}
