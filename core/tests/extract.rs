use mas_crawler_core::error::ExtractError;
use mas_crawler_core::extract::{ExtractConfig, Extractor, normalize_text};

#[test]
fn reports_missing_content() {
    let config = ExtractConfig {
        title_selector: "h1".into(),
        content_selector: "article".into(),
    };
    let result = Extractor::new(&config)
        .unwrap()
        .extract_document("<h1>Example</h1>", "https://example.com/");
    assert!(matches!(
        result,
        Err(ExtractError::NoMatch { field: "content" })
    ));
}

#[test]
fn normalizes_whitespace() {
    assert_eq!(normalize_text("  Привет\n\tмир!\u{00a0} "), "Привет мир!");
}

#[test]
fn normalizes_empty_text() {
    assert_eq!(normalize_text(""), "");
    assert_eq!(normalize_text(" \n\t"), "");
}

#[test]
fn preserves_inline_word_fragments() {
    let config = ExtractConfig {
        title_selector: "h1".into(),
        content_selector: "article".into(),
    };
    let document = Extractor::new(&config)
        .unwrap()
        .extract_document(
            "<h1>Rust</h1><article>own<b>er</b>ship</article>",
            "https://example.com/ownership",
        )
        .unwrap();
    assert_eq!(document.text, "ownership");
}

#[test]
fn extracts_article() {
    let html = r#"
                <html>
                    <body>
                        <nav>Home Contacts</nav>
                        <h1>Rust ownership</h1>
                        <article>
                            <p>Each value has an owner.</p>
                            <p>Ownership can be transferred.</p>
                        </article>
                    </body>
                </html>
            "#;
    let config = ExtractConfig {
        title_selector: String::from("h1"),
        content_selector: String::from("article"),
    };
    let document = Extractor::new(&config)
        .unwrap()
        .extract_document(html, "https://example.com/ownership")
        .unwrap();
    assert_eq!(document.url, "https://example.com/ownership");
    assert_eq!(document.title, "Rust ownership");
    assert_eq!(
        document.text,
        "Each value has an owner. Ownership can be transferred."
    );
    assert!(!document.text.contains("Contacts"));
}

#[test]
fn text_extraction() {
    let html = r#"
                <html>
                    <body>
                        <nav>Home Contacts</nav>
                        <h1>Rust ownership</h1>
                        <article>
                            <p>Hello</p><p>World</p>
                        </article>
                    </body>
                </html>
            "#;
    let config = ExtractConfig {
        title_selector: String::from("h1"),
        content_selector: String::from("article"),
    };
    let document = Extractor::new(&config)
        .unwrap()
        .extract_document(html, "https://example.com/ownership")
        .unwrap();
    assert_eq!(document.text, "Hello World");
}
