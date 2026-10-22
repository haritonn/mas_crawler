from ._native import (
    Document,
    ExtractError,
    ExtractionPreview,
    FetchError,
    FetchedPage,
    Fetcher,
    Link,
    LinkError,
    extract_document,
    extract_links,
    normalize_url,
    preview_extraction,
)

from pathlib import Path
from mas_crawler.selector_agent import propose_selectors, SelectorConfig


__all__ = [
    "Document",
    "ExtractError",
    "ExtractionPreview",
    "FetchError",
    "FetchedPage",
    "Fetcher",
    "Link",
    "LinkError",
    "extract_document",
    "extract_links",
    "normalize_url",
    "preview_extraction",
]


def main() -> None:
    fetcher = Fetcher()
    page = fetcher.fetch("https://doc.rust-lang.org/std/marker/trait.Copy.html")
    selectors = propose_selectors(page.html)
    print(selectors.model_dump())
    preview = preview_extraction(
        page.html,
        page.url,
        title_selector=selectors.title_selector,
        content_selector=selectors.content_selector,
    )
    print(preview.title, preview.content_matches, preview.text_preview)
