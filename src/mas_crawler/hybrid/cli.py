"""Search existing Tantivy and dense indexes with weighted RRF."""

import argparse
import json
from contextlib import closing
from pathlib import Path

from .._native import SearchIndex
from ..benchmark.experiments import SearchConfig
from .search import HybridSearch, _validate_fusion


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid BM25 + dense search using RRF")
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--sparse-top-k", type=int, default=100)
    parser.add_argument("--dense-top-k", type=int, default=100)
    parser.add_argument("--sparse-weight", type=float, default=1.0)
    parser.add_argument("--dense-weight", type=float, default=1.0)
    parser.add_argument("--rrf-k", type=float, default=60.0)
    parser.add_argument(
        "--config", type=Path, help="JSON file with Tantivy field weights"
    )
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    try:
        _validate_fusion(args.sparse_weight, args.dense_weight, args.rrf_k)
        if min(args.top_k, args.sparse_top_k, args.dense_top_k) < 1:
            raise ValueError("top-k and candidate depths must be positive")
    except ValueError as error:
        parser.error(str(error))
    config = (
        SearchConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
        if args.config is not None
        else None
    )

    # --help and argument validation need neither model imports nor a server.
    from qdrant_client import QdrantClient

    from ..dense import DenseSearch

    sparse = SearchIndex(str(args.index))
    with closing(QdrantClient(url=args.qdrant_url, timeout=60)) as client:
        dense = DenseSearch(args.build, client, device=args.device)
        search = HybridSearch(
            sparse,
            dense,
            sparse_top_k=args.sparse_top_k,
            dense_top_k=args.dense_top_k,
            sparse_weight=args.sparse_weight,
            dense_weight=args.dense_weight,
            rrf_k=args.rrf_k,
            sparse_config=config,
        )
        hits = search.search(args.query, top_k=args.top_k)
    print(json.dumps(hits, ensure_ascii=False, indent=2))
