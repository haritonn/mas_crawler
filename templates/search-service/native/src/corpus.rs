use std::collections::HashMap;
use std::io::{BufRead, BufReader};
use std::path::Path;

use anyhow::{Context, Result, ensure};

use crate::extract::Document;

pub fn load_documents(path: &Path) -> Result<Vec<Document>> {
    let reader = BufReader::new(
        std::fs::File::open(path)
            .with_context(|| format!("failed to open corpus {}", path.display()))?,
    );
    let mut documents = Vec::new();
    let mut urls = HashMap::new();
    for (offset, line) in reader.lines().enumerate() {
        let number = offset + 1;
        let line = line.with_context(|| format!("failed to read line {number}"))?;
        if line.trim().is_empty() {
            continue;
        }
        let document: Document = serde_json::from_str(&line)
            .with_context(|| format!("invalid JSON at line {number}"))?;
        for (name, value) in [
            ("url", &document.url),
            ("title", &document.title),
            ("text", &document.text),
        ] {
            ensure!(
                !value.trim().is_empty(),
                "line {number}: {name} must not be blank"
            );
        }
        if let Some(first) = urls.insert(document.url.clone(), number) {
            anyhow::bail!(
                "line {number}: duplicate URL {:?} (first seen at line {first})",
                document.url
            );
        }
        documents.push(document);
    }
    ensure!(!documents.is_empty(), "corpus is empty: {}", path.display());
    Ok(documents)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_invalid_corpora_with_line_numbers() {
        let valid = "{\"url\":\"https://example.com\",\"title\":\"Rust\",\"text\":\"Search\"}";
        let cases = [
            (String::new(), "empty", None),
            ("\n \n".to_owned(), "empty", None),
            (format!("{valid}\nnot json\n"), "invalid JSON", Some(2)),
            (format!("\n{valid}\n{valid}\n"), "duplicate URL", Some(3)),
            (
                "{\"url\":\" \",\"title\":\"Rust\",\"text\":\"Search\"}".to_owned(),
                "url",
                Some(1),
            ),
            (
                "{\"url\":\"u\",\"title\":\" \",\"text\":\"Search\"}".to_owned(),
                "title",
                Some(1),
            ),
            (
                "{\"url\":\"u\",\"title\":\"Rust\",\"text\":\"\\t\"}".to_owned(),
                "text",
                Some(1),
            ),
            (
                format!("{valid}\n{{\"url\":\"u\"}}"),
                "invalid JSON",
                Some(2),
            ),
        ];
        let directory = tempfile::tempdir().unwrap();
        let corpus = directory.path().join("corpus.jsonl");
        for (input, expected, line) in cases {
            std::fs::write(&corpus, input).unwrap();
            let error = format!("{:#}", load_documents(&corpus).unwrap_err());
            assert!(
                error.contains(expected),
                "{error:?} must contain {expected:?}"
            );
            if let Some(line) = line {
                assert!(error.contains(&format!("line {line}")), "{error}");
            }
        }
    }

    #[test]
    fn loads_jsonl_documents_preserving_fields() {
        let directory = tempfile::tempdir().unwrap();
        let corpus = directory.path().join("corpus.jsonl");
        std::fs::write(
            &corpus,
            "{\"url\":\"https://example.com\",\"title\":\"Rust\",\"text\":\"Rust search\"}\n",
        )
        .unwrap();
        let documents = load_documents(&corpus).unwrap();
        assert_eq!(documents.len(), 1);
        assert_eq!(documents[0].url, "https://example.com");
        assert_eq!(documents[0].title, "Rust");
        assert_eq!(documents[0].text, "Rust search");
    }
}
