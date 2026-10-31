use anyhow::Result;
use mas_crawler_core::{
    experiments::{ExperimentPlan, run_experiments},
    extract::Document,
    search::TantivyIndex,
};
use std::sync::Arc;

fn plan() -> Result<ExperimentPlan> {
    Ok(serde_json::from_str(
        r#"{
        "experiments": [
            {"name":"title", "config":{"title_weight":3.0,"text_weight":1.0}},
            {"name":"text", "config":{"title_weight":1.0,"text_weight":3.0}}
        ],
        "queries": ["rust", "", "missing"],
        "top_k": 2
    }"#,
    )?)
}

#[test]
fn reuses_open_index_for_named_configurations() -> Result<()> {
    let directory = tempfile::tempdir()?;
    let path = directory.path().join("index");
    let documents = [
        Document {
            url: "title".into(),
            title: "rust".into(),
            text: "other".into(),
        },
        Document {
            url: "text".into(),
            title: "other".into(),
            text: "rust".into(),
        },
    ];
    drop(TantivyIndex::create(&path, &documents)?);
    let index = Arc::new(TantivyIndex::open(&path)?);
    assert!(
        run_experiments(Arc::clone(&index), &plan()?, 0)
            .unwrap_err()
            .to_string()
            .contains("parallelism")
    );
    let results = run_experiments(Arc::clone(&index), &plan()?, 1)?;
    for parallelism in [2, 8] {
        let parallel = run_experiments(Arc::clone(&index), &plan()?, parallelism)?;
        assert_eq!(
            serde_json::to_value(&parallel)?,
            serde_json::to_value(&results)?
        );
    }
    assert_eq!(results.len(), 2);
    for (result, expected) in results.iter().zip(["title", "text"]) {
        assert_eq!(result.name, expected);
        assert_eq!(result.results[0].query, "rust");
        assert_eq!(result.results[0].hits.len(), 2);
        assert_eq!(result.results[0].hits[0].url, expected);
        assert!(result.results[1].hits.is_empty());
        assert!(result.results[2].hits.is_empty());
    }
    let mut zero_limit = plan()?;
    zero_limit.top_k = 0;
    let empty = run_experiments(Arc::clone(&index), &zero_limit, 2)?;
    assert!(
        empty
            .iter()
            .all(|result| result.results.iter().all(|query| query.hits.is_empty()))
    );

    let mut punctuation = plan()?;
    punctuation.queries = vec!["\"".into()];
    let results = run_experiments(Arc::clone(&index), &punctuation, 2)?;
    for result in results {
        assert_eq!(result.results[0].query, "\"");
        assert!(result.results[0].hits.is_empty());
    }
    assert_eq!(Arc::strong_count(&index), 1);
    Ok(())
}

#[test]
fn rejects_invalid_plans() -> Result<()> {
    let mut invalid = plan()?;
    invalid.experiments[1].name = "title".into();
    assert!(
        invalid
            .validate()
            .unwrap_err()
            .to_string()
            .contains("duplicate")
    );
    invalid = plan()?;
    invalid.experiments[0].name = " ".into();
    assert!(
        invalid
            .validate()
            .unwrap_err()
            .to_string()
            .contains("name is empty")
    );
    invalid = plan()?;
    invalid.experiments.clear();
    assert!(
        invalid
            .validate()
            .unwrap_err()
            .to_string()
            .contains("experiments list is empty")
    );
    invalid = plan()?;
    invalid.queries.clear();
    assert!(
        invalid
            .validate()
            .unwrap_err()
            .to_string()
            .contains("queries list is empty")
    );
    invalid = plan()?;
    invalid.experiments[0].config.title_weight = -1.0;
    assert!(format!("{:#}", invalid.validate().unwrap_err()).contains("nonnegative"));
    Ok(())
}
