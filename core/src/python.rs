//! Thin Python bindings; extraction and URL logic stay in the Rust core.
use pyo3::create_exception;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use std::sync::Arc;
use tokio::runtime::Runtime;

use crate::search::{SearchConfig, SearchEngine, TantivyEngine, TantivyIndex};
use crate::{crawler, error, experiments, extract, fetch, links};

create_exception!(mas_crawler, ExtractError, PyValueError);
create_exception!(mas_crawler, LinkError, PyValueError);
create_exception!(mas_crawler, FetchError, PyRuntimeError);

fn with_code(py: Python<'_>, exception: PyErr, code: &str) -> PyErr {
    match exception.value(py).setattr("code", code) {
        Ok(()) => exception,
        Err(error) => error,
    }
}

fn extract_error(py: Python<'_>, error: error::ExtractError) -> PyErr {
    let code = match &error {
        error::ExtractError::InvalidSelector { .. } => "invalid_selector",
        error::ExtractError::NoMatch { .. } => "no_match",
        error::ExtractError::EmptyContent => "empty_content",
    };
    with_code(py, ExtractError::new_err(error.to_string()), code)
}

fn link_error(py: Python<'_>, error: error::LinkError) -> PyErr {
    let code = match &error {
        error::LinkError::InvalidPageUrl { .. } => "invalid_url",
        error::LinkError::UnsupportedPageScheme { .. } => "unsupported_scheme",
    };
    with_code(py, LinkError::new_err(error.to_string()), code)
}

/// Reuse one HTTP client and Tokio runtime across synchronous fetch calls.
#[pyclass(name = "Fetcher", module = "mas_crawler._native")]
struct PyFetcher {
    client: reqwest::Client,
    runtime: Runtime,
}

#[pymethods]
impl PyFetcher {
    #[new]
    fn new(py: Python<'_>) -> PyResult<Self> {
        let result: anyhow::Result<Self> = py.detach(|| {
            let runtime = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()?;
            let client = runtime.block_on(async { fetch::build_client() })?;
            Ok(Self { client, runtime })
        });
        result.map_err(|error| {
            PyRuntimeError::new_err(format!("failed to create fetcher: {error:#}"))
        })
    }

    /// Download a page. This call releases the GIL but is not an asyncio coroutine.
    fn fetch(&self, py: Python<'_>, url: &str) -> PyResult<fetch::FetchedPage> {
        let url = links::normalize_url(url).map_err(|error| link_error(py, error))?;
        let result = py.detach(|| self.runtime.block_on(fetch::fetch_page(&self.client, &url)));
        match result {
            Ok(page) => Ok(page),
            Err(error) => {
                let status_code = error
                    .downcast_ref::<reqwest::Error>()
                    .and_then(|error| error.status())
                    .map(|status| status.as_u16());
                let exception = FetchError::new_err(format!("{error:#}"));
                let code = if status_code.is_some() {
                    "http_status"
                } else {
                    "request"
                };
                exception.value(py).setattr("code", code)?;
                exception.value(py).setattr("url", url)?;
                exception.value(py).setattr("status_code", status_code)?;
                Err(exception)
            }
        }
    }
}

/// Keep one read-only index open across Python searches and experiment batches.
#[pyclass(name = "SearchIndex", module = "mas_crawler._native")]
struct PySearchIndex {
    index: Arc<TantivyIndex>,
}

#[pymethods]
impl PySearchIndex {
    #[new]
    fn new(py: Python<'_>, index_path: &str) -> PyResult<Self> {
        py.detach(|| TantivyIndex::open(std::path::Path::new(index_path)))
            .map(|index| Self {
                index: Arc::new(index),
            })
            .map_err(|error| PyRuntimeError::new_err(format!("failed to open index: {error:#}")))
    }

    /// Return JSON search hits using optional JSON field weights.
    #[pyo3(signature = (query, top_k = 5, *, config_json = None))]
    fn search(
        &self,
        py: Python<'_>,
        query: &str,
        top_k: usize,
        config_json: Option<&str>,
    ) -> PyResult<String> {
        let config = match config_json {
            Some(value) => serde_json::from_str::<SearchConfig>(value).map_err(|error| {
                PyValueError::new_err(format!("invalid search config: {error}"))
            })?,
            None => SearchConfig::default(),
        };
        let engine = TantivyEngine::new(Arc::clone(&self.index), config)
            .map_err(|error| PyValueError::new_err(format!("invalid search config: {error:#}")))?;
        let result: anyhow::Result<String> = py.detach(|| {
            let hits = engine.search(query, top_k)?;
            Ok(serde_json::to_string(&hits)?)
        });
        result.map_err(|error| PyRuntimeError::new_err(format!("search failed: {error:#}")))
    }

    /// Execute the existing Rust experiment plan on this same open index.
    #[pyo3(signature = (plan_json, parallelism = 1))]
    fn run_experiments(
        &self,
        py: Python<'_>,
        plan_json: &str,
        parallelism: usize,
    ) -> PyResult<String> {
        let plan: experiments::ExperimentPlan = serde_json::from_str(plan_json)
            .map_err(|error| PyValueError::new_err(format!("invalid experiment plan: {error}")))?;
        let result: anyhow::Result<String> = py.detach(|| {
            let results =
                experiments::run_experiments(Arc::clone(&self.index), &plan, parallelism)?;
            Ok(serde_json::to_string(&results)?)
        });
        result.map_err(|error| PyRuntimeError::new_err(format!("experiments failed: {error:#}")))
    }
}

/// Normalize an absolute HTTP(S) URL, removing its fragment.
#[pyfunction(name = "normalize_url")]
fn py_normalize_url(py: Python<'_>, value: &str) -> PyResult<String> {
    py.detach(|| links::normalize_url(value))
        .map_err(|error| link_error(py, error))
}

/// Resolve and deduplicate HTTP(S) links using the final response URL.
#[pyfunction(name = "extract_links")]
fn py_extract_links(py: Python<'_>, html: &str, page_url: &str) -> PyResult<Vec<links::Link>> {
    py.detach(|| links::extract_links(html, page_url))
        .map_err(|error| link_error(py, error))
}

/// Extract the first matching title and content container from saved HTML.
#[pyfunction(name = "extract_document", signature = (html, url, *, title_selector, content_selector))]
fn py_extract_document(
    py: Python<'_>,
    html: &str,
    url: &str,
    title_selector: &str,
    content_selector: &str,
) -> PyResult<extract::Document> {
    let config = extract::ExtractConfig {
        title_selector: title_selector.to_owned(),
        content_selector: content_selector.to_owned(),
    };
    py.detach(|| extract::Extractor::new(&config)?.extract_document(html, url))
        .map_err(|error| extract_error(py, error))
}

/// Inspect selector matches and a bounded text sample without writing documents.
#[pyfunction(name = "preview_extraction", signature = (html, url, *, title_selector, content_selector, max_chars = 1000))]
fn py_preview_extraction(
    py: Python<'_>,
    html: &str,
    url: &str,
    title_selector: &str,
    content_selector: &str,
    max_chars: usize,
) -> PyResult<extract::ExtractionPreview> {
    let config = extract::ExtractConfig {
        title_selector: title_selector.to_owned(),
        content_selector: content_selector.to_owned(),
    };
    py.detach(|| {
        extract::Extractor::new(&config).map(|extractor| extractor.preview(html, url, max_chars))
    })
    .map_err(|error| extract_error(py, error))
}

/// Execute a saved plan, releasing the GIL for the entire crawl.
#[pyfunction(name = "crawl")]
fn py_crawl(py: Python<'_>, plan_json: &str, output: &str) -> PyResult<String> {
    let plan: crawler::CrawlPlan = serde_json::from_str(plan_json)
        .map_err(|error| PyValueError::new_err(format!("invalid crawl plan: {error}")))?;
    let result: anyhow::Result<String> = py.detach(|| {
        let runtime = Runtime::new()?;
        let report = runtime.block_on(crawler::crawl(&plan, std::path::Path::new(output)))?;
        Ok(serde_json::to_string(&report)?)
    });
    result.map_err(|error| PyRuntimeError::new_err(format!("{error:#}")))
}

#[pyfunction]
fn build_index(py: Python<'_>, corpus_path: &str, index_path: &str) -> PyResult<usize> {
    let result: anyhow::Result<usize> = py.detach(|| {
        let documents = crate::corpus::load_documents(std::path::Path::new(corpus_path))?;
        crate::search::TantivyIndex::create(std::path::Path::new(index_path), &documents)?;
        Ok(documents.len())
    });
    result.map_err(|error| PyRuntimeError::new_err(format!("{error:#}")))
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    module.add("ExtractError", py.get_type::<ExtractError>())?;
    module.add("LinkError", py.get_type::<LinkError>())?;
    module.add("FetchError", py.get_type::<FetchError>())?;
    module.add_class::<extract::Document>()?;
    module.add_class::<links::Link>()?;
    module.add_class::<extract::ExtractionPreview>()?;
    module.add_class::<fetch::FetchedPage>()?;
    module.add_class::<PyFetcher>()?;
    module.add_class::<PySearchIndex>()?;
    module.add_function(wrap_pyfunction!(py_normalize_url, module)?)?;
    module.add_function(wrap_pyfunction!(py_extract_links, module)?)?;
    module.add_function(wrap_pyfunction!(py_extract_document, module)?)?;
    module.add_function(wrap_pyfunction!(py_preview_extraction, module)?)?;
    module.add_function(wrap_pyfunction!(py_crawl, module)?)?;
    module.add_function(wrap_pyfunction!(build_index, module)?)?;
    Ok(())
}
