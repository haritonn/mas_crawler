from pydantic import BaseModel, Field

from .selector_agent import SelectorConfig


class CrawlPlan(BaseModel):
    seed_urls: list[str] = Field(
        min_length=1,
        description="Discovered entry URLs for deterministic link traversal",
    )
    scope_prefix: str = Field(
        description="Absolute URL prefix of the allowed directory, ending in /"
    )
    document_url_patterns: list[str] = Field(
        min_length=1,
        description="Python fnmatchcase patterns matched against URL paths, not full URLs",
    )
    selectors: SelectorConfig
    verified_urls: list[str] = Field(
        min_length=2,
        description="Distinct final URLs successfully checked with these exact selectors",
    )
    max_pages: int = Field(
        default=1000, gt=0, description="Bulk crawl download-attempt limit"
    )
