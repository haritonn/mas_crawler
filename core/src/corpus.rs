use anyhow::Result;
use futures_util::{StreamExt, stream};
use reqwest::Client;
use std::fs::OpenOptions;
use std::io::{BufWriter, Write};
use std::path::Path;

use crate::extract::{Document, ExtractConfig, extract_document};
use crate::fetch::fetch_page;

// Reading url's from &[String], saving pairs (urls, result) to the output path
pub async fn collect_corpus(
    client: &Client,
    urls: &[String],
    config: &ExtractConfig,
    output: &Path,
) -> Result<()> {
    if urls.is_empty() {
        anyhow::bail!("urls list is empty")
    }
    let file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(output)?;
    let mut writer = BufWriter::new(file);
    let requests = stream::iter(urls.iter()).map(|url| async move {
        let result = scrape_page(client, url, config).await;
        (url, result)
    });

    let mut results = requests.buffer_unordered(3);
    let mut succeeded = 0;
    let mut failed = 0;
    while let Some((url, result)) = results.next().await {
        match result {
            Ok(document) => {
                serde_json::to_writer(&mut writer, &document)?;
                writer.write_all(b"\n")?;
                succeeded += 1;
            }
            Err(error) => {
                eprintln!("failed to scrape {url}: {error:#}");
                failed += 1;
            }
        }
    }

    writer.flush()?;

    eprintln!("finished: {succeeded} succeeded, {failed} failed");

    if succeeded == 0 {
        anyhow::bail!("no documents were collected");
    }

    Ok(())
}

// Interface for scrapping single page. Better for collect_corpus
async fn scrape_page(client: &Client, url: &str, config: &ExtractConfig) -> Result<Document> {
    let page = fetch_page(client, url).await?;
    extract_document(&page.html, &page.url, config)
}
