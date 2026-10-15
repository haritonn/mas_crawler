use anyhow::Result;
use mas_crawler_core::{
    extract::Document,
    search::{SearchEngine, TantivyEngine},
};

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

    let engine = TantivyEngine::create(&index_path, &documents)?;

    let hits = engine.search("selector", 5)?;

    assert_eq!(hits.len(), 1);
    assert_eq!(hits[0].url, documents[0].url);
    assert_eq!(hits[0].title, "HTML");

    Ok(())
}
