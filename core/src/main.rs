use anyhow::Result;
use clap::Parser;
use mas_crawler_core::{corpus::collect_corpus, extract::ExtractConfig, fetch::build_client};
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long)]
    urls: PathBuf,

    #[arg(long)]
    config: PathBuf,

    #[arg(long)]
    output: PathBuf,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();
    let config_json = std::fs::read_to_string(&args.config)?;
    let config: ExtractConfig = serde_json::from_str(&config_json)?;
    let client = build_client()?;
    let input = fs::read_to_string(&args.urls)?;
    let lines: Vec<String> = input
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(str::to_owned)
        .collect();

    collect_corpus(&client, &lines, &config, &args.output).await?;
    Ok(())
}
