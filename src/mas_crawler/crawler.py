import json
from pathlib import Path
from typing import Any

from ._native import crawl
from .crawl_plan import CrawlPlan


def crawl_site(plan: CrawlPlan, output: str | Path) -> dict[str, Any]:
    """Execute a saved plan in Rust without model calls."""
    return json.loads(crawl(plan.model_dump_json(), str(output)))
