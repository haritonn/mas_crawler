use std::collections::HashSet;

use scraper::{Html, Selector};
use serde::Serialize;
use url::Url;

use crate::error::LinkError;
use crate::extract::extract_text;

#[derive(Debug, Serialize)]
pub struct Link {
    pub url: String,
    pub text: String,
}

/// Normalize an absolute HTTP(S) URL for identity comparisons.
/// Fragments are removed; query parameters and trailing slashes are preserved.
pub fn normalize_url(value: &str) -> Result<String, LinkError> {
    Ok(parse_page_url(value)?.into())
}

/// Extract HTTP(S) links using the final response URL as the page address.
/// Malformed hrefs and unsupported schemes are skipped. External links are
/// returned too; crawl policy is responsible for deciding which to follow.
/// Current-page links are omitted. Duplicate targets keep the first link text
/// and document order. This does not track URLs across separate calls.
/// The first base[href] is honored; an invalid base falls back to the page URL.
pub fn extract_links(html: &str, page_url: &str) -> Result<Vec<Link>, LinkError> {
    let page_url = parse_page_url(page_url)?;
    let page = Html::parse_document(html);
    let base_selector = Selector::parse("base[href]").expect("static base selector is valid");
    let base_url = page
        .select(&base_selector)
        .next()
        .and_then(|element| element.attr("href"))
        .and_then(|href| page_url.join(href.trim()).ok())
        .unwrap_or_else(|| page_url.clone());
    let selector = Selector::parse("a[href]").expect("static link selector is valid");
    let mut links = Vec::new();
    let mut seen = HashSet::new();
    seen.insert(page_url.as_str().to_owned());

    for element in page.select(&selector) {
        let href = element.attr("href").expect("selector requires href").trim();
        if href.is_empty() {
            continue;
        }
        let Ok(mut url) = base_url.join(href) else {
            continue;
        };
        if !matches!(url.scheme(), "http" | "https") {
            continue;
        }
        url.set_fragment(None);
        let url: String = url.into();
        if !seen.insert(url.clone()) {
            continue;
        }
        links.push(Link {
            url,
            text: extract_text(element),
        });
    }
    Ok(links)
}

fn parse_page_url(value: &str) -> Result<Url, LinkError> {
    let mut url = Url::parse(value).map_err(|source| LinkError::InvalidPageUrl {
        url: value.to_owned(),
        source,
    })?;
    if !matches!(url.scheme(), "http" | "https") {
        return Err(LinkError::UnsupportedPageScheme {
            scheme: url.scheme().to_owned(),
        });
    }
    url.set_fragment(None);
    Ok(url)
}
