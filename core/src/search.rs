use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::path::Path;

use std::sync::Arc;

use tantivy::collector::TopDocs;
use tantivy::query::QueryParser;
use tantivy::schema::{Field, STORED, Schema, TEXT, Value};
use tantivy::{Index, IndexReader, IndexWriter, TantivyDocument, doc};

use crate::extract::Document;

#[derive(Debug, Serialize)]
pub struct SearchHit {
    pub url: String,
    pub title: String,
    pub score: f32,
}

// Overall interface for search engine implementations
pub trait SearchEngine {
    fn search(&self, query: &str, top_k: usize) -> Result<Vec<SearchHit>>;
}

pub struct TantivyIndex {
    index: Index,
    reader: IndexReader,
    url: Field,
    title: Field,
    text: Field,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SearchConfig {
    pub title_weight: f32,
    pub text_weight: f32,
}

pub struct TantivyEngine {
    index: Arc<TantivyIndex>,
    config: SearchConfig,
}

impl Default for SearchConfig {
    fn default() -> Self {
        Self {
            title_weight: 1.0,
            text_weight: 1.0,
        }
    }
}

impl TantivyEngine {
    pub fn new(index: Arc<TantivyIndex>, config: SearchConfig) -> Result<Self> {
        config.validate()?;
        Ok(Self { index, config })
    }
}

impl SearchConfig {
    pub fn validate(&self) -> Result<()> {
        for (name, weight) in [
            ("title_weight", self.title_weight),
            ("text_weight", self.text_weight),
        ] {
            anyhow::ensure!(
                weight.is_finite() && weight >= 0.0,
                "{name} must be finite and nonnegative"
            );
        }
        anyhow::ensure!(
            self.title_weight > 0.0 || self.text_weight > 0.0,
            "at least one search weight must be positive"
        );
        Ok(())
    }
}

impl TantivyIndex {
    // Creating Tantivy search engine. Will automatically work in multithreading mode.
    pub fn create(path: &Path, documents: &[Document]) -> Result<Self> {
        if documents.is_empty() {
            anyhow::bail!("no documents in array");
        }
        let mut builder = Schema::builder();
        let url = builder.add_text_field("url", STORED);
        let title = builder.add_text_field("title", STORED | TEXT);
        let text = builder.add_text_field("text", TEXT);
        let schema = builder.build();

        std::fs::create_dir(path)?;
        let index = Index::create_in_dir(path, schema)?;
        let mut writer: IndexWriter = index.writer(50_000_000)?;
        for document in documents {
            writer.add_document(doc!(
                url => document.url.as_str(),
                title => document.title.as_str(),
                text => document.text.as_str(),
            ))?;
        }

        writer.commit()?;
        writer.wait_merging_threads()?;
        Self::from_index(index)
    }

    pub fn open(path: &Path) -> Result<Self> {
        Self::from_index(Index::open_in_dir(path)?)
    }

    fn from_index(index: Index) -> Result<Self> {
        let schema = index.schema();

        let url = schema.get_field("url")?;
        let title = schema.get_field("title")?;
        let text = schema.get_field("text")?;

        let reader = index.reader()?;

        Ok(Self {
            index,
            reader,
            url,
            title,
            text,
        })
    }
}

impl SearchEngine for TantivyEngine {
    fn search(&self, query: &str, top_k: usize) -> Result<Vec<SearchHit>> {
        if query.trim().is_empty() || top_k == 0 {
            return Ok(Vec::new());
        }
        let mut parser =
            QueryParser::for_index(&self.index.index, vec![self.index.title, self.index.text]);
        parser.set_field_boost(self.index.title, self.config.title_weight);
        parser.set_field_boost(self.index.text, self.config.text_weight);

        let query = parser.parse_query(query)?;
        let searcher = self.index.reader.searcher();
        let top_docs = searcher.search(&query, &TopDocs::with_limit(top_k).order_by_score())?;

        let mut hits = Vec::new();
        for (score, address) in top_docs {
            let document: TantivyDocument = searcher.doc(address)?;
            let url = document
                .get_first(self.index.url)
                .and_then(|val| val.as_str())
                .context("indexed doc has no url")?;
            let title = document
                .get_first(self.index.title)
                .and_then(|val| val.as_str())
                .context("indexed doc has no title")?;
            hits.push(SearchHit {
                url: url.to_owned(),
                title: title.to_owned(),
                score,
            });
        }

        Ok(hits)
    }
}
