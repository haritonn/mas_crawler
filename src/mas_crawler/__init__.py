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
    print("Hello from mas-crawler!")
