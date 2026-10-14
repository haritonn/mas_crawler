use anyhow::Result;
use reqwest::{Client, redirect::Policy};
use std::time::Duration;

#[derive(Debug)]
pub struct FetchedPage {
    pub url: String,
    pub html: String,
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

pub async fn fetch_page(client: &Client, url: &str) -> Result<FetchedPage> {
    let response = client.get(url).send().await?;
    let response = response.error_for_status()?;
    // handling redirection here: saving only last seen url
    let final_url = response.url().to_string();
    let html = response.text().await?;
    Ok(FetchedPage {
        url: final_url,
        html: html,
    })
}
