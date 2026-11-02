use pyo3::prelude::*;
use pyo3::types::PyDict;

fn module(py: Python<'_>) -> Bound<'_, PyModule> {
    let module = PyModule::new(py, "_native").unwrap();
    super::_native(&module).unwrap();
    module
}

fn corpus(directory: &std::path::Path) -> std::path::PathBuf {
    let path = directory.join("corpus.jsonl");
    std::fs::write(
        &path,
        concat!(
            "{\"url\":\"https://example.com/title\",\"title\":\"Rust\",\"text\":\"language\"}\n",
            "{\"url\":\"https://example.com/body\",\"title\":\"Language\",\"text\":\"Rust\"}\n",
        ),
    )
    .unwrap();
    path
}

#[test]
fn native_build_returns_count_and_never_overwrites() {
    Python::initialize();
    Python::attach(|py| {
        let directory = tempfile::tempdir().unwrap();
        let corpus = corpus(directory.path());
        let index = directory.path().join("index");
        let module = module(py);
        let build = module.getattr("build_index").unwrap();
        let args = (corpus.to_str().unwrap(), index.to_str().unwrap());
        assert_eq!(build.call1(args).unwrap().extract::<usize>().unwrap(), 2);
        let metadata = std::fs::read(index.join("meta.json")).unwrap();
        assert!(build.call1(args).is_err());
        assert_eq!(std::fs::read(index.join("meta.json")).unwrap(), metadata);
        let existing = directory.path().join("existing");
        std::fs::create_dir(&existing).unwrap();
        std::fs::write(existing.join("sentinel"), "untouched").unwrap();
        assert!(build.call1((args.0, existing.to_str().unwrap())).is_err());
        assert_eq!(
            std::fs::read_to_string(existing.join("sentinel")).unwrap(),
            "untouched"
        );
    });
}

#[test]
fn native_search_returns_json_and_accepts_keyword_weights() {
    Python::initialize();
    Python::attach(|py| {
        let directory = tempfile::tempdir().unwrap();
        let corpus = corpus(directory.path());
        let index = directory.path().join("index");
        let module = module(py);
        module
            .getattr("build_index")
            .unwrap()
            .call1((corpus.to_str().unwrap(), index.to_str().unwrap()))
            .unwrap();
        let class = module.getattr("SearchIndex").unwrap();
        assert_eq!(
            class
                .getattr("__module__")
                .unwrap()
                .extract::<String>()
                .unwrap(),
            "search_service._native"
        );
        let instance = class.call1((index.to_str().unwrap(),)).unwrap();
        let search = instance.getattr("search").unwrap();
        let result = search
            .call1(("Rust",))
            .unwrap()
            .extract::<String>()
            .unwrap();
        let hits: serde_json::Value = serde_json::from_str(&result).unwrap();
        assert_eq!(hits.as_array().unwrap().len(), 2);
        let hit = hits[0].as_object().unwrap();
        assert_eq!(hit.len(), 3);
        assert!(hit["url"].is_string());
        assert!(hit["title"].is_string());
        assert!(hit["score"].as_f64().unwrap() > 0.0);
        let kwargs = PyDict::new(py);
        for (title, text, expected) in [(10.0, 0.0, "title"), (0.0, 10.0, "body")] {
            kwargs.set_item("title_weight", title).unwrap();
            kwargs.set_item("text_weight", text).unwrap();
            let result = search
                .call(("Rust", 1), Some(&kwargs))
                .unwrap()
                .extract::<String>()
                .unwrap();
            let hits: serde_json::Value = serde_json::from_str(&result).unwrap();
            assert_eq!(hits.as_array().unwrap().len(), 1);
            assert_eq!(hits[0]["url"], format!("https://example.com/{expected}"));
        }
        for args in [(" ", 5), ("Rust", 0), ("nonexistent", 5)] {
            assert_eq!(
                search.call1(args).unwrap().extract::<String>().unwrap(),
                "[]"
            );
        }
        for (title, text) in [
            (-1.0, 1.0),
            (f32::NAN, 1.0),
            (1.0, f32::INFINITY),
            (0.0, 0.0),
        ] {
            kwargs.set_item("title_weight", title).unwrap();
            kwargs.set_item("text_weight", text).unwrap();
            let error = search.call(("Rust",), Some(&kwargs)).unwrap_err();
            assert!(error.is_instance_of::<pyo3::exceptions::PyValueError>(py));
        }
        assert!(search.call1(("Rust", 5, 1.0, 1.0)).is_err());
        assert!(search.call1(("Rust", -1)).is_err());
        assert!(
            class
                .call1((directory.path().join("missing").to_str().unwrap(),))
                .is_err()
        );
    });
}
