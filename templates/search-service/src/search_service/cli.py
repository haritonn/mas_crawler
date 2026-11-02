"""Build and serve commands for the standalone project."""

import argparse
import json
import sys
from pathlib import Path

from .build import build


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="search-service")
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser(
        "build", help="Build a new index from the corpus"
    )
    build_parser.add_argument("--config", type=Path, default=Path("search.toml"))
    build_parser.add_argument(
        "--output", type=Path, help="New index directory (relative to CWD)"
    )
    serve_parser = commands.add_parser(
        "serve", help="Serve search using an existing index"
    )
    serve_parser.add_argument("--config", type=Path, default=Path("search.toml"))
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            print(
                json.dumps(
                    build(args.config, args.output), ensure_ascii=False, indent=2
                )
            )
        else:
            import uvicorn

            from .app import create_app

            uvicorn.run(create_app(args.config), host=args.host, port=args.port)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"search-service: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
