use anyhow::Result;
use mas_crawler_core::{
    experiments::{ExperimentPlan, run_experiments},
    extract::Document,
    search::TantivyIndex,
};

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
fn runs_named_configurations_on_one_persisted_index() -> Result<()> {
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
    let results = run_experiments(&path, &plan()?, 1)?;
    for parallelism in [2, 8] {
        let parallel = run_experiments(&path, &plan()?, parallelism)?;
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
    let empty = run_experiments(&path, &zero_limit, 2)?;
    assert!(
        empty
            .iter()
            .all(|result| result.results.iter().all(|query| query.hits.is_empty()))
    );

    let mut malformed = plan()?;
    malformed.queries = vec!["\"".into()];
    let error = run_experiments(&path, &malformed, 2).unwrap_err();
    assert!(format!("{error:#}").contains("experiment \"title\""));
    Ok(())
}

#[test]
fn rejects_invalid_plans_before_opening_index() -> Result<()> {
    let directory = tempfile::tempdir()?;
    let missing = directory.path().join("missing");
    let mut invalid = plan()?;
    invalid.experiments[1].name = "title".into();
    assert!(
        run_experiments(&missing, &invalid, 1)
            .unwrap_err()
            .to_string()
            .contains("duplicate")
    );
    invalid = plan()?;
    invalid.experiments[0].name = " ".into();
    assert!(
        run_experiments(&missing, &invalid, 1)
            .unwrap_err()
            .to_string()
            .contains("name is empty")
    );
    invalid = plan()?;
    invalid.experiments.clear();
    assert!(
        run_experiments(&missing, &invalid, 1)
            .unwrap_err()
            .to_string()
            .contains("experiments list is empty")
    );
    invalid = plan()?;
    invalid.queries.clear();
    assert!(
        run_experiments(&missing, &invalid, 1)
            .unwrap_err()
            .to_string()
            .contains("queries list is empty")
    );
    invalid = plan()?;
    invalid.experiments[0].config.title_weight = -1.0;
    assert!(
        format!("{:#}", run_experiments(&missing, &invalid, 2).unwrap_err())
            .contains("nonnegative")
    );
    assert!(
        run_experiments(&missing, &plan()?, 0)
            .unwrap_err()
            .to_string()
            .contains("parallelism")
    );
    Ok(())
}
