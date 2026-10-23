"""Types for the native Rust extension. Build the extension with maturin."""

def crawl(plan_json: str, output: str) -> str:
    """Execute a plan without LLM calls and return a JSON crawl report."""
    ...

class ExtractError(ValueError):
    code: str

class LinkError(ValueError):
    code: str

class FetchError(RuntimeError):
    code: str
    url: str
    status_code: int | None

class Fetcher:
    """Reusable synchronous HTTP client; use asyncio.to_thread in async code."""
    def __init__(self) -> None: ...
    def fetch(self, url: str) -> FetchedPage: ...

class FetchedPage:
    @property
    def url(self) -> str: ...
    @property
    def html(self) -> str: ...
    @property
    def status_code(self) -> int: ...
    @property
    def content_type(self) -> str | None: ...

class ExtractionPreview:
    @property
    def url(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def title_matches(self) -> int: ...
    @property
    def content_matches(self) -> int: ...
    @property
    def text_preview(self) -> str: ...
    @property
    def text_length(self) -> int: ...
    @property
    def truncated(self) -> bool: ...

class Document:
    """Read-only result returned by extract_document; not directly constructible."""
    @property
    def url(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def text(self) -> str: ...

class Link:
    """Read-only link returned by extract_links; not directly constructible."""
    @property
    def url(self) -> str: ...
    @property
    def text(self) -> str: ...

def normalize_url(value: str) -> str: ...
def extract_links(html: str, page_url: str) -> list[Link]: ...
def extract_document(
    html: str,
    url: str,
    *,
    title_selector: str,
    content_selector: str,
) -> Document: ...
def preview_extraction(
    html: str,
    url: str,
    *,
    title_selector: str,
    content_selector: str,
    max_chars: int = 1000,
) -> ExtractionPreview: ...
