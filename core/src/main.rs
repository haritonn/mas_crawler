use anyhow::Result;
use mas_crawler_core::fetch::{build_client, fetch_page};

#[tokio::main]
async fn main() -> Result<()> {
    let client = build_client()?;
    let page = fetch_page(&client, "https://docs.rs/scraper/latest/scraper/index.html").await?;

    println!("URL: {}", page.url);
    println!("{}", page.html);

    Ok(())
}
