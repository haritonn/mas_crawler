use anyhow::Result;
use serde_json::{Value, json};
use std::process::{Command, Output};
use wiremock::{
    Mock, MockServer, ResponseTemplate,
    matchers::{method, path},
};

fn cli() -> Command {
    Command::new(env!("CARGO_BIN_EXE_mas-crawler-core"))
}

fn assert_success(output: &Output) {
    assert!(
        output.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn indexes_corpus_and_searches_in_another_process() -> Result<()> {
    let directory = tempfile::tempdir()?;
    let corpus = directory.path().join("corpus.jsonl");
    let index = directory.path().join("index");
    let documents = [
        json!({"url": "https://example.test/html", "title": "HTML", "text": "Select elements using a CSS selector."}),
        json!({"url": "https://example.test/images", "title": "Images", "text": "Download image files."}),
    ];
    std::fs::write(&corpus, format!("{}\n\n{}\n", documents[0], documents[1]))?;

    let output = cli()
        .arg("index")
        .arg("--corpus")
        .arg(&corpus)
        .arg("--index")
        .arg(&index)
        .output()?;
    assert_success(&output);
    assert!(output.stdout.is_empty());

    let output = cli()
        .arg("search")
        .arg("--index")
        .arg(&index)
        .args(["--query", "selector", "--top-k", "1"])
        .output()?;
    assert_success(&output);
    let hits: Vec<Value> = serde_json::from_slice(&output.stdout)?;
    assert_eq!(hits.len(), 1);
    assert_eq!(hits[0]["url"], "https://example.test/html");
    assert_eq!(hits[0]["title"], "HTML");
    assert!(hits[0]["score"].as_f64().unwrap() > 0.0);

    for query in ["", "zzzzmissing"] {
        let output = cli()
            .arg("search")
            .arg("--index")
            .arg(&index)
            .args(["--query", query])
            .output()?;
        assert_success(&output);
        assert_eq!(serde_json::from_slice::<Value>(&output.stdout)?, json!([]));
    }
    let output = cli()
        .arg("search")
        .arg("--index")
        .arg(&index)
        .args(["--query", "selector", "--top-k", "0"])
        .output()?;
    assert_success(&output);
    assert_eq!(serde_json::from_slice::<Value>(&output.stdout)?, json!([]));

    let output = cli()
        .arg("index")
        .arg("--corpus")
        .arg(&corpus)
        .arg("--index")
        .arg(&index)
        .output()?;
    assert!(
        !output.status.success(),
        "existing index must not be overwritten"
    );
    Ok(())
}

#[test]
fn reports_invalid_jsonl_line_without_creating_index() -> Result<()> {
    let directory = tempfile::tempdir()?;
    let corpus = directory.path().join("corpus.jsonl");
    let index = directory.path().join("index");
    std::fs::write(
        &corpus,
        "{\"url\":\"u\",\"title\":\"t\",\"text\":\"body\"}\nnot-json\n",
    )?;
    let output = cli()
        .arg("index")
        .arg("--corpus")
        .arg(&corpus)
        .arg("--index")
        .arg(&index)
        .output()?;
    assert!(!output.status.success());
    assert!(output.stdout.is_empty());
    assert!(String::from_utf8_lossy(&output.stderr).contains("line 2"));
    assert!(!index.exists());
    Ok(())
}

#[test]
fn rejects_empty_corpus() -> Result<()> {
    let directory = tempfile::tempdir()?;
    let corpus = directory.path().join("empty.jsonl");
    let index = directory.path().join("index");
    std::fs::write(&corpus, "\n \n")?;
    let output = cli()
        .arg("index")
        .arg("--corpus")
        .arg(&corpus)
        .arg("--index")
        .arg(&index)
        .output()?;
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("empty"));
    assert!(!index.exists());
    Ok(())
}

#[tokio::test]
async fn collects_documents_through_cli() -> Result<()> {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/article"))
        .respond_with(
            ResponseTemplate::new(200)
                .insert_header("Content-Type", "text/html")
                .set_body_string("<h1>Example</h1><article>Hello world</article>"),
        )
        .expect(1)
        .mount(&server)
        .await;
    let directory = tempfile::tempdir()?;
    let urls = directory.path().join("urls.txt");
    let config = directory.path().join("config.json");
    let corpus = directory.path().join("corpus.jsonl");
    std::fs::write(&urls, format!("\n{}/article\n\n", server.uri()))?;
    std::fs::write(
        &config,
        r#"{"title_selector":"h1","content_selector":"article"}"#,
    )?;
    let mut command = cli();
    command
        .arg("collect")
        .arg("--urls")
        .arg(&urls)
        .arg("--config")
        .arg(&config)
        .arg("--output")
        .arg(&corpus);
    let output = tokio::task::spawn_blocking(move || command.output()).await??;
    assert_success(&output);
    assert!(output.stdout.is_empty());
    let contents = std::fs::read_to_string(&corpus)?;
    let documents: Vec<Value> = contents
        .lines()
        .map(serde_json::from_str)
        .collect::<serde_json::Result<_>>()?;
    assert_eq!(documents.len(), 1);
    assert_eq!(documents[0]["url"], format!("{}/article", server.uri()));
    assert_eq!(documents[0]["text"], "Hello world");
    server.verify().await;
    Ok(())
}
