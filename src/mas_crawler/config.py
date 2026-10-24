"""Application settings; site-specific crawl rules remain in CrawlPlan."""

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LLMConfig(Settings):
    model: str = Field(default="deepseek/deepseek-v4.1-flash", min_length=1)
    base_url: str | None = Field(default=None, min_length=1)


class ExplorerConfig(Settings):
    max_pages: int = Field(default=5, gt=0)
    links_limit: int = Field(default=50, gt=0)
    text_preview_chars: int = Field(default=4000, gt=0)
    extraction_preview_chars: int = Field(default=1000, gt=0)
    html_fragment_chars: int = Field(default=12000, gt=0)
    recursion_limit: int = Field(default=40, gt=0)
    correction_attempts: int = Field(default=1, ge=0)


class SelectorAgentConfig(Settings):
    max_attempts: int = Field(default=3, gt=0)


class AppConfig(Settings):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    explorer: ExplorerConfig = Field(default_factory=ExplorerConfig)
    selector: SelectorAgentConfig = Field(default_factory=SelectorAgentConfig)


def load_config(path: str | Path | None = None) -> AppConfig:
    """Read TOML from an explicit path or optional ./config.toml, without caching."""
    config_path = Path(path) if path is not None else Path("config.toml")
    if path is None and not config_path.exists():
        return AppConfig()
    with config_path.open("rb") as file:
        return AppConfig.model_validate(tomllib.load(file))
