use anyhow::{Result, anyhow};
use scraper::{Html, Selector};
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize)]
pub struct ExtractConfig {
    pub title_selector: String,
    pub content_selector: String,
}

#[derive(Debug, Serialize)]
pub struct Document {
    pub url: String,
    pub title: String,
    pub text: String,
}

pub fn extract_document(html: &str, url: &str, cfg: &ExtractConfig) -> Result<Document> {
    let page = Html::parse_document(html);
    let title_selector = parse_selector(&cfg.title_selector)?;
    let content_selector = parse_selector(&cfg.content_selector)?;

    let title_element = page
        .select(&title_selector)
        .next()
        .ok_or_else(|| anyhow!("no elements matching title selector"))?;

    let content_element = page
        .select(&content_selector)
        .next()
        .ok_or_else(|| anyhow!("no elements matching content selector"))?;

    let raw_title: String = title_element.text().collect();
    let raw_text: String = content_element.text().collect();
    let title = normalize_text(&raw_title);
    let text = normalize_text(&raw_text);

    if text.is_empty() {
        anyhow::bail!("extracted content is empty")
    }
    Ok(Document {
        url: url.to_owned(),
        title,
        text,
    })
}

// Parses a CSS selector.
// Scraper has own type of errors, so should be mapped to anyhow type.
fn parse_selector(value: &str) -> Result<Selector> {
    Selector::parse(value).map_err(|err| anyhow!("invalid css selector: {value:?}: {err:?}"))
}

// Trims whitespace and collapses whitespace sequences into a single space.
// (kinda bullshit now, should be refactored in future)
pub fn normalize_text(text: &str) -> String {
    let mut result = String::new();

    for word in text.split_whitespace() {
        if !result.is_empty() {
            result.push(' ');
        }

        result.push_str(word);
    }

    result
}

#[cfg(test)]
mod tests {
    use super::*;

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
        let document = extract_document(
            "<h1>Rust</h1><article>own<b>er</b>ship</article>",
            "https://example.com/ownership",
            &config,
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
        let document = extract_document(html, "https://example.com/ownership", &config).unwrap();
        assert_eq!(document.url, "https://example.com/ownership");
        assert_eq!(document.title, "Rust ownership");
        assert_eq!(
            document.text,
            "Each value has an owner. Ownership can be transferred."
        );
        assert!(!document.text.contains("Contacts"));
    }
}
