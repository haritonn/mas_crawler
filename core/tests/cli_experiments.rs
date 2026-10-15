use anyhow::Result;
use mas_crawler_core::{extract::Document, search::TantivyIndex};
use serde_json::{Value, json};
use std::process::Command;

#[test]
fn searches_with_json_config_and_runs_experiment_plan() -> Result<()> {
    let directory = tempfile::tempdir()?;
    let index = directory.path().join("index");
    let config = directory.path().join("config.json");
    let plan = directory.path().join("plan.json");
    drop(TantivyIndex::create(
        &index,
        &[
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
        ],
    )?);
    std::fs::write(&config, r#"{"title_weight":1,"text_weight":3}"#)?;
    let output = Command::new(env!("CARGO_BIN_EXE_mas-crawler-core"))
        .arg("search")
        .arg("--index")
        .arg(&index)
        .arg("--config")
        .arg(&config)
        .args(["--query", "rust"])
        .output()?;
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let hits: Vec<Value> = serde_json::from_slice(&output.stdout)?;
    assert_eq!(hits[0]["url"], "text");

    std::fs::write(
        &plan,
        serde_json::to_vec(&json!({
            "experiments": [
                {"name":"title", "config":{"title_weight":3,"text_weight":1}},
                {"name":"text", "config":{"title_weight":1,"text_weight":3}}
            ], "queries":["rust"], "top_k":1
        }))?,
    )?;
    let output = Command::new(env!("CARGO_BIN_EXE_mas-crawler-core"))
        .arg("experiment")
        .arg("--index")
        .arg(&index)
        .arg("--plan")
        .arg(&plan)
        .args(["--parallelism", "1"])
        .output()?;
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let results: Vec<Value> = serde_json::from_slice(&output.stdout)?;
    assert_eq!(results.len(), 2);
    for (result, name) in results.iter().zip(["title", "text"]) {
        assert_eq!(result["name"], name);
        assert_eq!(result["results"][0]["hits"][0]["url"], name);
    }

    std::fs::write(&config, r#"{"title_weight":-1,"text_weight":1}"#)?;
    let output = Command::new(env!("CARGO_BIN_EXE_mas-crawler-core"))
        .arg("search")
        .arg("--index")
        .arg(&index)
        .arg("--config")
        .arg(&config)
        .args(["--query", "rust"])
        .output()?;
    assert!(!output.status.success());
    assert!(output.stdout.is_empty());
    assert!(String::from_utf8_lossy(&output.stderr).contains("nonnegative"));
    Ok(())
}
