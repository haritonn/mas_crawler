use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::{collections::HashSet, path::Path, sync::Arc};

use crate::search::{SearchConfig, SearchEngine, SearchHit, TantivyEngine, TantivyIndex};

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExperimentPlan {
    pub experiments: Vec<ExperimentSpec>,
    pub queries: Vec<String>,
    pub top_k: usize,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExperimentSpec {
    pub name: String,
    pub config: SearchConfig,
}

#[derive(Debug, Serialize)]
pub struct ExperimentResult {
    pub name: String,
    pub config: SearchConfig,
    pub results: Vec<QueryResult>,
}

#[derive(Debug, Serialize)]
pub struct QueryResult {
    pub query: String,
    pub hits: Vec<SearchHit>,
}

impl ExperimentPlan {
    pub fn validate(&self) -> Result<()> {
        anyhow::ensure!(!self.experiments.is_empty(), "experiments list is empty");
        anyhow::ensure!(!self.queries.is_empty(), "queries list is empty");
        let mut names = HashSet::new();
        for experiment in &self.experiments {
            anyhow::ensure!(
                !experiment.name.trim().is_empty(),
                "experiment name is empty"
            );
            anyhow::ensure!(
                names.insert(&experiment.name),
                "duplicate experiment name: {}",
                experiment.name
            );
            experiment
                .config
                .validate()
                .with_context(|| format!("invalid config for experiment {}", experiment.name))?;
        }
        Ok(())
    }
}

/// Open one index and execute named search configurations.
pub fn run_experiments(
    path: &Path,
    plan: &ExperimentPlan,
    parallelism: usize,
) -> Result<Vec<ExperimentResult>> {
    plan.validate()?;
    anyhow::ensure!(parallelism > 0, "parallelism must be positive");
    let index = Arc::new(
        TantivyIndex::open(path)
            .with_context(|| format!("failed to open index {}", path.display()))?,
    );
    if parallelism == 1 {
        return plan
            .experiments
            .iter()
            .map(|spec| run_one(Arc::clone(&index), spec, &plan.queries, plan.top_k))
            .collect();
    }

    let mut results = Vec::new();
    for batch in plan.experiments.chunks(parallelism) {
        let completed = std::thread::scope(|scope| {
            let mut handles = Vec::new();
            for spec in batch {
                let index = Arc::clone(&index);
                handles.push(scope.spawn(move || run_one(index, spec, &plan.queries, plan.top_k)));
            }
            // Join the entire batch before propagating an error.
            handles
                .into_iter()
                .map(|handle| {
                    handle
                        .join()
                        .unwrap_or_else(|_| Err(anyhow::anyhow!("experiment worker panicked")))
                })
                .collect::<Vec<_>>()
        });
        for result in completed {
            results.push(result?);
        }
    }
    Ok(results)
}

fn run_one(
    index: Arc<TantivyIndex>,
    spec: &ExperimentSpec,
    queries: &[String],
    top_k: usize,
) -> Result<ExperimentResult> {
    let engine = TantivyEngine::new(index, spec.config.clone())?;
    let mut results = Vec::with_capacity(queries.len());
    for query in queries {
        let hits = engine
            .search(query, top_k)
            .with_context(|| format!("experiment {:?}, query {:?}", spec.name, query))?;
        results.push(QueryResult {
            query: query.clone(),
            hits,
        });
    }
    Ok(ExperimentResult {
        name: spec.name.clone(),
        config: spec.config.clone(),
        results,
    })
}
