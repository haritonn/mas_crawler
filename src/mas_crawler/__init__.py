import json
from argparse import ArgumentParser
from pathlib import Path

from ._native import (
    Document,
    ExtractError,
    ExtractionPreview,
    FetchedPage,
    Fetcher,
    FetchError,
    Link,
    LinkError,
    extract_document,
    extract_links,
    normalize_url,
    preview_extraction,
)
from .crawl_plan import CrawlPlan
from .crawler import crawl_site
from .explorer import explore_site

__all__ = [
    "Document",
    "ExtractError",
    "ExtractionPreview",
    "FetchError",
    "FetchedPage",
    "Fetcher",
    "Link",
    "LinkError",
    "crawl_site",
    "extract_document",
    "extract_links",
    "normalize_url",
    "preview_extraction",
]


def main() -> None:
    parser = ArgumentParser(description="Prepare or execute a crawl plan")
    parser.add_argument(
        "url", nargs="?", default="https://doc.rust-lang.org/std/index.html"
    )
    parser.add_argument(
        "--goal",
        default="Найди страницы с описанием трейтов стандартной библиотеки Rust.",
    )
    parser.add_argument(
        "--plan", type=Path, help="Execute a saved plan without LLM calls"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        args.output = Path("corpus.jsonl" if args.plan else "crawl-plan.json")
    if args.output.exists():
        parser.error(f"{args.output} already exists; choose another --output path")

    if args.plan:
        plan = CrawlPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
        print(json.dumps(crawl_site(plan, args.output), ensure_ascii=False, indent=2))
        return

    report = explore_site(args.url, args.goal)
    if report.plan is not None:
        with args.output.open("x", encoding="utf-8") as file:
            file.write(report.plan.model_dump_json(indent=2))
    print(report.model_dump_json(indent=2))
