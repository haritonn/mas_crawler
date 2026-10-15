use anyhow::Result;
use mas_crawler_core::{
    extract::Document,
    search::{SearchConfig, SearchEngine, TantivyEngine, TantivyIndex},
};
use std::sync::Arc;

#[test]
fn finds_document_by_body_text() -> Result<()> {
    let directory = tempfile::tempdir()?;
    let index_path = directory.path().join("index");

    let documents = vec![
        Document {
            url: "https://example.test/html".into(),
            title: "HTML".into(),
            text: "Select elements using a CSS selector.".into(),
        },
        Document {
            url: "https://example.test/images".into(),
            title: "Images".into(),
            text: "Download image files.".into(),
        },
    ];

    let index = TantivyIndex::create(&index_path, &documents)?;
    let index = Arc::new(index);
    assert!(
        TantivyEngine::new(
            Arc::clone(&index),
            SearchConfig {
                title_weight: -1.0,
                text_weight: 1.0,
            }
        )
        .is_err()
    );
    let engine = TantivyEngine::new(index, SearchConfig::default())?;

    let hits = engine.search("selector", 5)?;

    assert_eq!(hits.len(), 1);
    assert_eq!(hits[0].url, documents[0].url);
    assert_eq!(hits[0].title, "HTML");
    assert!(hits[0].score > 0.0);

    Ok(())
}

#[test]
fn validates_search_weights() -> Result<()> {
    for input in [
        r#"{"title_weight":1}"#,
        r#"{"title_weight":1,"text_weight":1,"typo":2}"#,
        r#"{"title_weight":null,"text_weight":1}"#,
    ] {
        assert!(serde_json::from_str::<SearchConfig>(input).is_err());
    }
    let config: SearchConfig = serde_json::from_str(r#"{"title_weight":3.0,"text_weight":1.0}"#)?;
    config.validate()?;
    for (title_weight, text_weight) in [
        (-1.0, 1.0),
        (1.0, -1.0),
        (0.0, 0.0),
        (f32::NAN, 1.0),
        (1.0, f32::INFINITY),
    ] {
        assert!(
            SearchConfig {
                title_weight,
                text_weight
            }
            .validate()
            .is_err()
        );
    }
    SearchConfig {
        title_weight: 0.0,
        text_weight: 1.0,
    }
    .validate()?;
    Ok(())
}
