use anyhow::Result;
use mas_crawler_core::{corpus::collect_corpus, extract::ExtractConfig, fetch::build_client};
use serde_json::Value;
use wiremock::{
    Mock, MockServer, ResponseTemplate,
    matchers::{method, path},
};

#[tokio::test]
async fn keep_successfull_pages() -> Result<()> {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/article"))
        .respond_with(
            ResponseTemplate::new(200)
                .insert_header("Content-Type", "text/html; charset=utf-8")
                .set_body_string(include_str!("fixtures/corpus/page.html")),
        )
        .mount(&server)
        .await;

    Mock::given(method("GET"))
        .and(path("/missing"))
        .respond_with(ResponseTemplate::new(404))
        .expect(1)
        .mount(&server)
        .await;

    let config: ExtractConfig =
        serde_json::from_str(include_str!("fixtures/corpus/scraper-config.json"))?;

    let article_url = format!("{}/article", server.uri());

    let urls = vec![article_url.clone(), format!("{}/missing", server.uri())];
    let directory = tempfile::tempdir()?;
    let output = directory.path().join("corpus.jsonl");
    let client = build_client()?;
    let report = collect_corpus(&client, &urls, &config, &output).await?;
    assert_eq!(report.succeeded, 1);
    assert_eq!(report.failures.len(), 1);
    assert_eq!(report.failures[0].url, urls[1]);
    let error = report.failures[0]
        .error
        .downcast_ref::<reqwest::Error>()
        .unwrap();
    assert_eq!(error.status(), Some(reqwest::StatusCode::NOT_FOUND));

    server.verify().await;
    let contents = std::fs::read_to_string(&output)?;
    let documents: Vec<Value> = contents
        .lines()
        .map(serde_json::from_str)
        .collect::<serde_json::Result<_>>()?;

    assert_eq!(documents.len(), 1);
    assert_eq!(documents[0]["url"], article_url);
    assert_eq!(documents[0]["title"], "Example");
    assert_eq!(documents[0]["text"], "Example Hello world");

    Ok(())
}

#[tokio::test]
async fn failed_pages() -> Result<()> {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/missing"))
        .respond_with(ResponseTemplate::new("404"))
        .expect(1)
        .mount(&server)
        .await;

    let config: ExtractConfig =
        serde_json::from_str(include_str!("fixtures/corpus/scraper-config.json"))?;

    let missing_url = format!("{}/missing", server.uri());
    let urls = vec![missing_url.clone()];
    let directory = tempfile::tempdir()?;
    let output = directory.path().join("corpus.jsonl");
    let client = build_client()?;
    let report = collect_corpus(&client, &urls, &config, &output).await?;
    server.verify().await;
    assert_eq!(report.succeeded, 0);
    assert_eq!(report.failures.len(), 1);
    assert_eq!(report.failures[0].url, missing_url);
    assert!(
        report.failures[0]
            .error
            .downcast_ref::<reqwest::Error>()
            .is_some()
    );
    assert!(std::fs::read_to_string(output)?.is_empty());
    Ok(())
}

#[tokio::test]
async fn rejects_invalid_selectors_before_creating_output_or_fetching() -> Result<()> {
    let server = MockServer::start().await;
    let directory = tempfile::tempdir()?;
    let client = build_client()?;
    for (title_selector, content_selector) in [("[", "article"), ("h1", "[")] {
        let config = ExtractConfig {
            title_selector: title_selector.into(),
            content_selector: content_selector.into(),
        };
        let output = directory.path().join("corpus.jsonl");
        let error = collect_corpus(&client, &[server.uri()], &config, &output)
            .await
            .unwrap_err();
        assert!(matches!(
            error.downcast_ref::<mas_crawler_core::error::ExtractError>(),
            Some(mas_crawler_core::error::ExtractError::InvalidSelector { .. })
        ));
        assert!(!output.exists());
    }
    assert!(server.received_requests().await.unwrap().is_empty());
    Ok(())
}

#[tokio::test]
async fn does_not_overwrite_existing_corpus() -> Result<()> {
    let directory = tempfile::tempdir()?;
    let output = directory.path().join("corpus.jsonl");

    let original = "{\"marker\":\"keep me\"}\n";
    std::fs::write(&output, original)?;
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/article"))
        .respond_with(
            ResponseTemplate::new(200)
                .insert_header("Content-Type", "text/html; charset=utf-8")
                .set_body_string(include_str!("fixtures/corpus/page.html")),
        )
        .mount(&server)
        .await;
    let config: ExtractConfig =
        serde_json::from_str(include_str!("fixtures/corpus/scraper-config.json"))?;

    let article_url = format!("{}/article", server.uri());

    let urls = vec![article_url];
    let client = build_client()?;

    let error = collect_corpus(&client, &urls, &config, &output)
        .await
        .expect_err("collection must not overwrite an existing corpus");
    let io_error = error
        .downcast_ref::<std::io::Error>()
        .expect("existing output must cause an I/O error");
    assert_eq!(io_error.kind(), std::io::ErrorKind::AlreadyExists);
    assert_eq!(std::fs::read_to_string(&output)?, original);
    assert!(
        server
            .received_requests()
            .await
            .expect("request recording must be enabled")
            .is_empty(),
        "collection must reject existing output before sending requests"
    );

    Ok(())
}
