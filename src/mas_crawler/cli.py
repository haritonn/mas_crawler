import json
from argparse import ArgumentParser
from pathlib import Path

from langchain_core.tracers.langchain import wait_for_all_tracers

from .benchmark import accept_benchmark, prepare_benchmark
from .config import load_config
from .crawling import CrawlPlan, crawl_site, explore_site
from .pipeline import build_search_system, prepare_dataset


def main() -> None:
    parser = ArgumentParser(
        description="Analyze a website, build a search index, or prepare a benchmark"
    )
    parser.add_argument(
        "--config", type=Path, help="Application TOML config (default: ./config.toml)"
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

    dataset = commands.add_parser(
        "dataset", help="Build a corpus and index, then prepare annotation tasks"
    )
    dataset.add_argument("url")
    dataset.add_argument("--goal", required=True)
    dataset.add_argument("--run-dir", type=Path, required=True)
    dataset.add_argument("--max-pairs", type=int, default=100)

    benchmark = commands.add_parser(
        "benchmark", help="Prepare and accept annotation CSV"
    )
    benchmark_commands = benchmark.add_subparsers(
        dest="benchmark_command", required=True
    )
    prepare = benchmark_commands.add_parser(
        "prepare", help="Generate a new annotation package"
    )
    prepare.add_argument("--corpus", type=Path, required=True)
    prepare.add_argument("--index", type=Path, required=True)
    prepare.add_argument("--goal", required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--max-pairs", type=int, default=100)
    prepare.add_argument("--sample-size", type=int)
    prepare.add_argument("--candidates-per-query", type=int, default=5)
    prepare.add_argument("--max-chars", type=int, default=12000)
    prepare.add_argument("--seed", type=int, default=42)

    accept = benchmark_commands.add_parser(
        "accept", help="Validate labels and freeze dev/test"
    )
    accept.add_argument("--package-dir", type=Path, required=True)
    accept.add_argument("--annotations", type=Path, required=True)
    accept.add_argument("--test-fraction", type=float, default=0.3)
    accept.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.command == "build":
        if args.plan and (args.url or args.goal):
            parser.error("build accepts either URL with --goal, or --plan")
        if not args.plan and (not args.url or not args.goal):
            parser.error("build requires URL and --goal, or --plan")

    try:
        if args.command == "benchmark":
            if args.benchmark_command == "prepare":
                result = prepare_benchmark(
                    args.corpus,
                    args.index,
                    args.goal,
                    args.output_dir,
                    max_pairs=args.max_pairs,
                    sample_size=args.sample_size,
                    candidates_per_query=args.candidates_per_query,
                    max_chars=args.max_chars,
                    seed=args.seed,
                    config=load_config(args.config),
                )
            else:
                result = accept_benchmark(
                    args.package_dir,
                    args.annotations,
                    test_fraction=args.test_fraction,
                    seed=args.seed,
                )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

        config = load_config(args.config)

        if args.command == "dataset":
            result = prepare_dataset(
                url=args.url,
                goal=args.goal,
                run_dir=args.run_dir,
                max_pairs=args.max_pairs,
                app_config=config,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if args.command == "analyze":
            if args.output.exists():
                parser.error(f"{args.output} already exists; choose another --output")
            report = explore_site(args.url, args.goal, app_config=config)
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
                app_config=config,
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
