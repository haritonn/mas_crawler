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
from mas_crawler.selector_agent import configure_extraction, SelectorConfig
from mas_crawler.explorer import explore_site


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
    report = explore_site(
        "https://doc.rust-lang.org/std/index.html",
        "Найди страницы с описанием трейтов STL Rust.",
    )
    print(report.model_dump_json(indent=2))
