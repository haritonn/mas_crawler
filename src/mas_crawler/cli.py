import json
from argparse import ArgumentParser
from pathlib import Path

from langchain_core.tracers.langchain import wait_for_all_tracers

from .crawl_plan import CrawlPlan
from .crawler import crawl_site
from .explorer import explore_site
from .pipeline import build_search_system


def main() -> None:
    parser = ArgumentParser(
        description="Analyze a website, crawl it, or build a search index"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    analyze = commands.add_parser(
        "analyze", help="Prepare a crawl plan using the model"
    )
    analyze.add_argument("url")
    analyze.add_argument("--goal", required=True)
    analyze.add_argument("--output", type=Path, default=Path("crawl-plan.json"))

    crawl = commands.add_parser("crawl", help="Collect a corpus without model calls")
    crawl.add_argument("--plan", type=Path, required=True)
    crawl.add_argument("--output", type=Path, default=Path("corpus.jsonl"))

    build = commands.add_parser(
        "build", help="Build a search index from a URL or saved plan"
    )
    build.add_argument("url", nargs="?")
    build.add_argument("--goal")
    build.add_argument("--plan", type=Path)
    build.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "build":
        if args.plan and (args.url or args.goal):
            parser.error("build accepts either URL with --goal, or --plan")
        if not args.plan and (not args.url or not args.goal):
            parser.error("build requires URL and --goal, or --plan")

    try:
        if args.command == "analyze":
            if args.output.exists():
                parser.error(f"{args.output} already exists; choose another --output")
            report = explore_site(args.url, args.goal)
            if report.plan is not None:
                with args.output.open("x", encoding="utf-8") as file:
                    file.write(report.plan.model_dump_json(indent=2))
            print(report.model_dump_json(indent=2))
            if report.plan is None:
                parser.exit(1)
            return

        if args.command == "crawl":
            plan = CrawlPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
            result = crawl_site(plan, args.output)
        else:
            plan = (
                CrawlPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
                if args.plan
                else None
            )
            result = build_search_system(
                url=plan.seed_urls[0] if plan is not None else args.url,
                goal=args.goal or "",
                run_dir=args.run_dir,
                plan=plan,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "crawl" and result["succeeded"] == 0:
            parser.exit(1)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    finally:
        wait_for_all_tracers()


if __name__ == "__main__":
    main()
