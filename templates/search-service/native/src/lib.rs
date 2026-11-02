mod corpus;
mod extract;
mod search;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use std::path::Path;
use std::sync::Arc;

use crate::search::{SearchConfig, SearchEngine, TantivyEngine, TantivyIndex};

#[pyclass(name = "SearchIndex", module = "search_service._native")]
struct PySearchIndex {
    index: Arc<TantivyIndex>,
}

#[pymethods]
impl PySearchIndex {
    #[new]
    fn new(py: Python<'_>, index_path: &str) -> PyResult<Self> {
        py.detach(|| TantivyIndex::open(Path::new(index_path)))
            .map(|index| Self {
                index: Arc::new(index),
            })
            .map_err(|error| PyRuntimeError::new_err(format!("failed to open index: {error:#}")))
    }

    #[pyo3(signature = (query, top_k = 5, *, title_weight = 1.0, text_weight = 1.0))]
    fn search(
        &self,
        py: Python<'_>,
        query: &str,
        top_k: usize,
        title_weight: f32,
        text_weight: f32,
    ) -> PyResult<String> {
        py.detach(|| {
            let config = SearchConfig {
                title_weight,
                text_weight,
            };
            let engine = TantivyEngine::new(Arc::clone(&self.index), config).map_err(|error| {
                PyValueError::new_err(format!("invalid search config: {error:#}"))
            })?;
            let hits = engine
                .search(query, top_k)
                .map_err(|error| PyRuntimeError::new_err(format!("search failed: {error:#}")))?;
            serde_json::to_string(&hits)
                .map_err(|error| PyRuntimeError::new_err(format!("failed to encode hits: {error}")))
        })
    }
}

#[pyfunction]
fn build_index(py: Python<'_>, corpus_path: &str, index_path: &str) -> PyResult<usize> {
    let result: anyhow::Result<usize> = py.detach(|| {
        let documents = corpus::load_documents(Path::new(corpus_path))?;
        // TantivyIndex::create uses create_dir, so even concurrent builders cannot overwrite.
        search::TantivyIndex::create(Path::new(index_path), &documents)?;
        Ok(documents.len())
    });
    result.map_err(|error| PyRuntimeError::new_err(format!("failed to build index: {error:#}")))
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<PySearchIndex>()?;
    module.add_function(wrap_pyfunction!(build_index, module)?)?;
    Ok(())
}

#[cfg(test)]
mod tests;
