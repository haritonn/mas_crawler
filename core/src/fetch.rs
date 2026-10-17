use anyhow::Result;
use reqwest::{Client, redirect::Policy};
use std::time::Duration;

#[derive(Debug)]
#[cfg_attr(
    feature = "python",
    pyo3::pyclass(frozen, get_all, module = "mas_crawler._native")
)]
pub struct FetchedPage {
    pub url: String,
    pub html: String,
    pub status_code: u16,
    pub content_type: Option<String>,
}

// Building client for fetching pages
pub fn build_client() -> Result<Client> {
    let client = Client::builder()
        .user_agent("mas-crawler/0.1")
        .timeout(Duration::from_secs(20))
        .redirect(Policy::limited(5))
        .build()?;

    Ok(client)
}

// Fetching single page via client and specified url
// Should be used as agent tool in future
pub async fn fetch_page(client: &Client, url: &str) -> Result<FetchedPage> {
    let response = client.get(url).send().await?;
    let response = response.error_for_status()?;
    // Saving only last seen url. Hence, handling possible redirections
    let final_url = response.url().to_string();
    let status_code = response.status().as_u16();
    let content_type = response
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .map(str::to_owned);
    let html = response.text().await?;
    Ok(FetchedPage {
        url: final_url,
        html,
        status_code,
        content_type,
    })
}
