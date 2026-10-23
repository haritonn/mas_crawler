use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use mas_crawler_core::{
    corpus::{collect_corpus, load_documents},
    crawler::{self, CrawlPlan},
    experiments::{ExperimentPlan, run_experiments},
    extract::ExtractConfig,
    fetch::build_client,
    search::{SearchConfig, SearchEngine, TantivyEngine, TantivyIndex},
};
use std::fs;
use std::io::Write;
use std::path::PathBuf;
use std::sync::Arc;

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
    /// Execute a saved crawl plan without model calls.
    Crawl {
        #[arg(long)]
        plan: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
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
        /// JSON search weights; omit to use equal weights.
        #[arg(long)]
        config: Option<PathBuf>,
    },
    /// Run named search configurations on one shared index.
    Experiment {
        #[arg(long)]
        index: PathBuf,
        #[arg(long)]
        plan: PathBuf,
        /// Maximum concurrent experiments; 1 runs sequentially.
        #[arg(long, default_value_t = 1)]
        parallelism: usize,
    },
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();

    match args.command {
        Command::Crawl { plan, output } => {
            let input = fs::read_to_string(&plan)
                .with_context(|| format!("failed to read plan {}", plan.display()))?;
            let plan: CrawlPlan = serde_json::from_str(&input).context("invalid crawl plan")?;
            let report = crawler::crawl(&plan, &output).await?;
            let mut stdout = std::io::stdout().lock();
            serde_json::to_writer(&mut stdout, &report)?;
            writeln!(stdout)?;
        }
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
            let report = collect_corpus(&client, &urls, &config, &output).await?;
            for failure in &report.failures {
                eprintln!("failed to scrape {}: {:#}", failure.url, failure.error);
            }
            eprintln!(
                "finished: {} succeeded, {} failed",
                report.succeeded,
                report.failures.len()
            );
            anyhow::ensure!(report.succeeded > 0, "no documents were collected");
        }
        Command::Index { corpus, index } => {
            let documents = load_documents(&corpus)?;
            TantivyIndex::create(&index, &documents)
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
            config,
        } => {
            let config = match config {
                Some(path) => serde_json::from_str::<SearchConfig>(
                    &fs::read_to_string(&path)
                        .with_context(|| format!("failed to read config {}", path.display()))?,
                )
                .context("invalid search configuration")?,
                None => SearchConfig::default(),
            };
            let search_index = TantivyIndex::open(&index)
                .with_context(|| format!("failed to open index: {}", index.display()))?;
            let engine = TantivyEngine::new(Arc::new(search_index), config)?;
            let hits = engine.search(&query, top_k)?;
            let mut stdout = std::io::stdout().lock();
            serde_json::to_writer(&mut stdout, &hits)?;
            writeln!(stdout)?;
        }
        Command::Experiment {
            index,
            plan,
            parallelism,
        } => {
            let input = fs::read_to_string(&plan)
                .with_context(|| format!("failed to read plan {}", plan.display()))?;
            let plan: ExperimentPlan =
                serde_json::from_str(&input).context("invalid experiment plan")?;
            plan.validate()?;
            anyhow::ensure!(parallelism > 0, "parallelism must be positive");
            let search_index = TantivyIndex::open(&index)
                .with_context(|| format!("failed to open index {}", index.display()))?;
            let results = run_experiments(Arc::new(search_index), &plan, parallelism)?;
            let mut stdout = std::io::stdout().lock();
            serde_json::to_writer(&mut stdout, &results)?;
            writeln!(stdout)?;
        }
    }
    Ok(())
}
