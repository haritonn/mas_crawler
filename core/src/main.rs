use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use mas_crawler_core::{
    corpus::{collect_corpus, load_documents},
    extract::ExtractConfig,
    fetch::build_client,
    search::{SearchEngine, TantivyEngine},
};
use std::fs;
use std::io::Write;
use std::path::PathBuf;

#[derive(Debug, Parser)]
#[command(
    name = "mas-crawler-core",
    version,
    about = "Collect documents, build an index, and search it"
)]
struct Args {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Collect pages from a URL list into a new JSONL file.
    Collect {
        #[arg(long)]
        urls: PathBuf,
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
    /// Build a new index directory from a JSONL corpus.
    Index {
        #[arg(long)]
        corpus: PathBuf,
        #[arg(long)]
        index: PathBuf,
    },
    /// Search an existing index and print a JSON array of results.
    Search {
        #[arg(long)]
        index: PathBuf,
        #[arg(long)]
        query: String,
        #[arg(long, default_value_t = 5)]
        top_k: usize,
    },
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();

    match args.command {
        Command::Collect {
            urls,
            config,
            output,
        } => {
            let config_json = fs::read_to_string(&config)
                .with_context(|| format!("failed to read config {}", config.display()))?;
            let config: ExtractConfig =
                serde_json::from_str(&config_json).context("invalid extraction configuration")?;
            let input = fs::read_to_string(&urls)
                .with_context(|| format!("failed to read URL list {}", urls.display()))?;
            let urls: Vec<String> = input
                .lines()
                .map(str::trim)
                .filter(|line| !line.is_empty())
                .map(str::to_owned)
                .collect();
            let client = build_client()?;
            collect_corpus(&client, &urls, &config, &output).await?;
        }
        Command::Index { corpus, index } => {
            let documents = load_documents(&corpus)?;
            TantivyEngine::create(&index, &documents)
                .with_context(|| format!("failed to build index {}", index.display()))?;
            eprintln!(
                "Indexed {} documents into {}",
                documents.len(),
                index.display()
            );
        }
        Command::Search {
            index,
            query,
            top_k,
        } => {
            let engine = TantivyEngine::open(&index)
                .with_context(|| format!("failed to open index {}", index.display()))?;
            let hits = engine.search(&query, top_k)?;
            let mut stdout = std::io::stdout().lock();
            serde_json::to_writer(&mut stdout, &hits)?;
            writeln!(stdout)?;
        }
    }
    Ok(())
}
