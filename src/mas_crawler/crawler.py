import json
from pathlib import Path
from typing import Any

from langsmith import traceable

from ._native import crawl
from .crawl_plan import CrawlPlan
from .observability import record_metadata


@traceable(name="crawl_site", tags=["mas-crawler", "crawl"])
def crawl_site(plan: CrawlPlan, output: str | Path) -> dict[str, Any]:
    """Execute a saved plan in Rust without model calls."""
    record_metadata(scope_prefix=plan.scope_prefix, max_pages=plan.max_pages)
    report = json.loads(crawl(plan.model_dump_json(), str(output)))
    record_metadata(
        failure_count=len(report["failures"]),
        empty_corpus=report["succeeded"] == 0,
        partial_failure=bool(report["failures"]) and report["succeeded"] > 0,
    )
    return report
