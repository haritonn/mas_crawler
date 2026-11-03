"""Command-line entry points for dense indexing and search."""

import argparse
import json
from contextlib import closing
from pathlib import Path

from qdrant_client import QdrantClient

from .build import build_dense
from .config import EmbeddingProfile
from .index import DenseSearch, upload_dense


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and query a dense search index")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--corpus", type=Path, required=True)
    build.add_argument("--profile", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--chunk-size", type=int, default=192)
    build.add_argument("--overlap", type=int, default=32)
    build.add_argument("--batch-size", type=int, default=32)
    build.add_argument("--device", default="cpu")
    for command in ("upload", "search"):
        sub = commands.add_parser(command)
        sub.add_argument("--build", type=Path, required=True)
        sub.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
        if command == "search":
            sub.add_argument("--query", required=True)
            sub.add_argument("--top-k", type=int, default=10)
            sub.add_argument("--device", default="cpu")
    args = parser.parse_args()
    if args.command == "build":
        profile = EmbeddingProfile.model_validate_json(
            args.profile.read_text(encoding="utf-8")
        )
        result = build_dense(
            args.corpus,
            args.output,
            profile,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            batch_size=args.batch_size,
            device=args.device,
        )
    else:
        with closing(QdrantClient(url=args.qdrant_url, timeout=60)) as client:
            if args.command == "upload":
                result = upload_dense(args.build, client)
            else:
                result = DenseSearch(args.build, client, device=args.device).search(
                    args.query, top_k=args.top_k
                )
    print(json.dumps(result, ensure_ascii=False, indent=2))
