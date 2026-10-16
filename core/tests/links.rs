use mas_crawler_core::error::LinkError;
use mas_crawler_core::links::{extract_links, normalize_url};

#[test]
fn skips_unusable_links_without_losing_valid_candidates() {
    let links = extract_links(
        r#"<a>No href</a><a href="">Empty</a><a href="   ">Whitespace</a>
           <a href="mailto:user@example.com">Mail</a>
           <a href="tel:123">Phone</a><a href="javascript:void(0)">JS</a>
           <a href="data:text/plain,test">Data</a><a href="ftp://example.com/file">FTP</a>
           <a href="http://[">Malformed</a>
           <a href=" search?q=rust&amp;page=2#results "> Search </a>"#,
        "https://docs.example/3/",
    )
    .unwrap();

    assert_eq!(links.len(), 1);
    assert_eq!(links[0].url, "https://docs.example/3/search?q=rust&page=2");
    assert_eq!(links[0].text, "Search");
}

#[test]
fn rejects_invalid_or_non_http_page_urls() {
    assert!(matches!(
        extract_links("<a href='/page'>Page</a>", "not a URL"),
        Err(LinkError::InvalidPageUrl { .. })
    ));
    assert!(matches!(
        normalize_url("relative/page"),
        Err(LinkError::InvalidPageUrl { .. })
    ));
    assert!(matches!(
        extract_links("", "file:///tmp/page.html"),
        Err(LinkError::UnsupportedPageScheme { scheme }) if scheme == "file"
    ));
    assert!(matches!(
        normalize_url("ftp://example.com/"),
        Err(LinkError::UnsupportedPageScheme { .. })
    ));
}

#[test]
fn invalid_first_base_falls_back_to_page_url() {
    let links = extract_links(
        r#"<base href="http://["><base href="https://ignored.example/">
           <a href="os.html">OS</a>"#,
        "https://docs.example/3/",
    )
    .unwrap();

    assert_eq!(links.len(), 1);
    assert_eq!(links[0].url, "https://docs.example/3/os.html");
}

#[test]
fn returns_empty_list_when_no_links_are_found() {
    assert!(
        extract_links("<p>Text only</p>", "https://docs.example/")
            .unwrap()
            .is_empty()
    );
}

#[test]
fn resolves_links_against_first_base_href() {
    let links = extract_links(
        r##"<base href="../library/"><base href="https://ignored.example/">
            <a href="os.html">OS</a><a href="#index">Library index</a>"##,
        "https://docs.example/3/tutorial/index.html",
    )
    .unwrap();

    assert_eq!(links.len(), 2);
    assert_eq!(links[0].url, "https://docs.example/3/library/os.html");
    assert_eq!(links[1].url, "https://docs.example/3/library/");
}

#[test]
fn normalizes_url_identity_without_changing_query_or_trailing_slash() {
    assert_eq!(
        normalize_url("HTTPS://Docs.Example:443/3/tutorial/../library/?page=2#part").unwrap(),
        "https://docs.example/3/library/?page=2"
    );
    assert_ne!(
        normalize_url("https://docs.example/page").unwrap(),
        normalize_url("https://docs.example/page/").unwrap()
    );
}

#[test]
fn deduplicates_links_and_skips_current_page_preserving_first_occurrence() {
    let links = extract_links(
        r##"<a href="#section">This page</a>
            <a href="index.html">Same page</a>
            <a href="os.html#first">First</a>
            <a href="https://DOCS.example:443/3/os.html#second">Duplicate</a>
            <a href="os.html?view=full">Other query</a>"##,
        "https://docs.example/3/index.html#top",
    )
    .unwrap();

    assert_eq!(links.len(), 2);
    assert_eq!(links[0].url, "https://docs.example/3/os.html");
    assert_eq!(links[0].text, "First");
    assert_eq!(links[1].url, "https://docs.example/3/os.html?view=full");
}

#[test]
fn resolves_links_and_extracts_normalized_text() {
    let links = extract_links(
        r#"<a href="../library/os.html#files"> OS <b>module</b> </a>
           <a href="/3/library/sys.html">System</a>
           <a href="//other.example/docs">External</a>"#,
        "https://docs.example/3/tutorial/index.html",
    )
    .unwrap();

    assert_eq!(links.len(), 3);
    assert_eq!(links[0].url, "https://docs.example/3/library/os.html");
    assert_eq!(links[0].text, "OS module");
    assert_eq!(links[1].url, "https://docs.example/3/library/sys.html");
    assert_eq!(links[2].url, "https://other.example/docs");
}
