use anyhow::{Result, anyhow};
use scraper::{ElementRef, Html, Node, Selector};
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize)]
pub struct ExtractConfig {
    pub title_selector: String,
    pub content_selector: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Document {
    pub url: String,
    pub title: String,
    pub text: String,
}

/// Reusable extraction rules with selectors parsed at construction time.
pub struct Extractor {
    title_selector: Selector,
    content_selector: Selector,
}

impl Extractor {
    pub fn new(config: &ExtractConfig) -> Result<Self> {
        Ok(Self {
            title_selector: parse_selector(&config.title_selector)?,
            content_selector: parse_selector(&config.content_selector)?,
        })
    }

    /// Extract the first matching title and content container.
    pub fn extract_document(&self, html: &str, url: &str) -> Result<Document> {
        let page = Html::parse_document(html);
        let title_element = page
            .select(&self.title_selector)
            .next()
            .ok_or_else(|| anyhow!("no elements matching title selector"))?;
        let content_element = page
            .select(&self.content_selector)
            .next()
            .ok_or_else(|| anyhow!("no elements matching content selector"))?;
        let title = extract_text(title_element);
        let text = extract_text(content_element);
        if text.is_empty() {
            anyhow::bail!("extracted content is empty")
        }
        Ok(Document {
            url: url.to_owned(),
            title,
            text,
        })
    }
}

/// One-off extraction; reuse Extractor when processing multiple pages.
pub fn extract_document(html: &str, url: &str, cfg: &ExtractConfig) -> Result<Document> {
    Extractor::new(cfg)?.extract_document(html, url)
}

// Parses a CSS selector.
// Scraper has own type of errors, so should be mapped to anyhow type.
fn parse_selector(value: &str) -> Result<Selector> {
    Selector::parse(value).map_err(|err| anyhow!("invalid css selector: {value:?}: {err:?}"))
}

// Extracting text from scraper nodes.
pub fn extract_text(element: ElementRef<'_>) -> String {
    let mut raw_text = String::new();
    append_text(element, &mut raw_text);
    normalize_text(&raw_text)
}

// Core function for appending extracted text to output.
fn append_text(element: ElementRef<'_>, output: &mut String) {
    for child in element.children() {
        match child.value() {
            Node::Text(text) => output.push_str(text),

            Node::Element(_) => {
                if let Some(child_element) = ElementRef::wrap(child) {
                    let tag = child_element.value().name();

                    match tag {
                        "script" | "style" => continue,
                        "br" => output.push(' '),
                        _ => {
                            // sorry
                            let is_block = matches!(
                                tag,
                                "p" | "div"
                                    | "article"
                                    | "section"
                                    | "h1"
                                    | "h2"
                                    | "h3"
                                    | "h4"
                                    | "h5"
                                    | "h6"
                                    | "ul"
                                    | "ol"
                                    | "li"
                                    | "blockquote"
                            );

                            if is_block {
                                output.push(' ');
                            }

                            append_text(child_element, output);

                            if is_block {
                                output.push(' ');
                            }
                        }
                    }
                }
            }

            _ => {}
        }
    }
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
