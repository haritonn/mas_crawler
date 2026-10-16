use anyhow::{Context, Result};
use futures_util::{StreamExt, stream};
use reqwest::Client;
use std::fs::{self, OpenOptions};
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::Path;

use crate::extract::{Document, ExtractConfig, Extractor};
use crate::fetch::fetch_page;

#[derive(Debug)]
pub struct CollectReport {
    pub succeeded: usize,
    pub failures: Vec<PageFailure>,
}

#[derive(Debug)]
pub struct PageFailure {
    pub url: String,
    pub error: anyhow::Error,
}

/// Write collected documents to a new JSONL file and report page-level failures.
/// Even if every page fails, return the report. Setup and write errors return Err.
/// On failure, the output file may be empty or contain partial results.
pub async fn collect_corpus(
    client: &Client,
    urls: &[String],
    config: &ExtractConfig,
    output: &Path,
) -> Result<CollectReport> {
    if urls.is_empty() {
        anyhow::bail!("urls list is empty")
    }
    let extractor = Extractor::new(config)?;
    let file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(output)?;
    let mut writer = BufWriter::new(file);
    let requests = stream::iter(urls.iter()).map(|url| {
        let extractor = &extractor;
        async move {
            let result = scrape_page(client, url, extractor).await;
            (url, result)
        }
    });

    let mut results = requests.buffer_unordered(3);
    let mut report = CollectReport {
        succeeded: 0,
        failures: Vec::new(),
    };
    while let Some((url, result)) = results.next().await {
        match result {
            Ok(document) => {
                serde_json::to_writer(&mut writer, &document)?;
                writer.write_all(b"\n")?;
                report.succeeded += 1;
            }
            Err(error) => {
                report.failures.push(PageFailure {
                    url: url.clone(),
                    error,
                });
            }
        }
    }

    writer.flush()?;

    Ok(report)
}

// Interface for scrapping single page. Better for collect_corpus
async fn scrape_page(client: &Client, url: &str, extractor: &Extractor) -> Result<Document> {
    let page = fetch_page(client, url).await?;
    Ok(extractor.extract_document(&page.html, &page.url)?)
}

// Load documents from specified path
pub fn load_documents(path: &Path) -> Result<Vec<Document>> {
    let file = fs::File::open(path)
        .with_context(|| format!("failed to open corpus {}", path.display()))?;
    let mut documents = Vec::new();

    for (position, line) in BufReader::new(file).lines().enumerate() {
        let line_number = position + 1;
        let line = line
            .with_context(|| format!("failed to read {} at line {line_number}", path.display()))?;
        if line.trim().is_empty() {
            continue;
        }
        let document = serde_json::from_str(&line).with_context(|| {
            format!(
                "invalid document in {} at line {line_number}",
                path.display()
            )
        })?;
        documents.push(document);
    }

    if documents.is_empty() {
        anyhow::bail!("corpus {} is empty", path.display());
    }
    Ok(documents)
}
