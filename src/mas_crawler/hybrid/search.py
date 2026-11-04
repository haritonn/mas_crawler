"""Combine document-level lexical and dense rankings by exact URL."""

from __future__ import annotations

import json
from math import isfinite
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._native import SearchIndex
    from ..benchmark.experiments import SearchConfig
    from ..dense import DenseSearch


def _validate_fusion(sparse_weight: float, dense_weight: float, rrf_k: float) -> None:
    for name, weight in (
        ("sparse_weight", sparse_weight),
        ("dense_weight", dense_weight),
    ):
        if not isfinite(weight) or weight < 0:
            raise ValueError(f"{name} must be finite and nonnegative")
    if sparse_weight == 0 and dense_weight == 0:
        raise ValueError("At least one channel weight must be positive")
    if not isfinite(rrf_k) or rrf_k <= 0:
        raise ValueError("rrf_k must be finite and positive")


def rrf_fusion(
    sparse_hits: list[dict],
    dense_hits: list[dict],
    *,
    top_k: int = 10,
    sparse_weight: float = 1.0,
    dense_weight: float = 1.0,
    rrf_k: float = 60.0,
) -> list[dict]:
    """Fuse one-based ranks; raw channel scores are retained only for debugging."""
    _validate_fusion(sparse_weight, dense_weight, rrf_k)
    if top_k < 1:
        raise ValueError("top_k must be positive")
    results = {}
    for channel, hits, weight in (
        ("sparse", sparse_hits, sparse_weight),
        ("dense", dense_hits, dense_weight),
    ):
        if weight == 0:
            continue
        seen = set()
        for hit in hits:
            url = hit["url"]
            if url in seen:
                continue
            seen.add(url)
            rank = len(seen)
            result = results.setdefault(
                url,
                {
                    "url": url,
                    "title": hit["title"],
                    "score": 0.0,
                    "sparse_rank": None,
                    "dense_rank": None,
                    "sparse_score": None,
                    "dense_score": None,
                },
            )
            result["score"] += weight / (rrf_k + rank)
            result[f"{channel}_rank"] = rank
            result[f"{channel}_score"] = hit["score"]
    return sorted(results.values(), key=lambda hit: (-hit["score"], hit["url"]))[:top_k]


class HybridSearch:
    """Reuse an open Tantivy index and dense retriever over the same corpus.

    Channel depths are document counts, independent of the final cutoff. A zero
    weight disables that backend; failures in enabled backends propagate.
    The caller owns the backends and the dense retriever's Qdrant client.
    """

    def __init__(
        self,
        sparse: SearchIndex,
        dense: DenseSearch,
        *,
        sparse_top_k: int = 100,
        dense_top_k: int = 100,
        sparse_weight: float = 1.0,
        dense_weight: float = 1.0,
        rrf_k: float = 60.0,
        sparse_config: SearchConfig | None = None,
    ) -> None:
        _validate_fusion(sparse_weight, dense_weight, rrf_k)
        if sparse_top_k < 1 or dense_top_k < 1:
            raise ValueError("sparse_top_k and dense_top_k must be positive")
        self.sparse = sparse
        self.dense = dense
        self.sparse_top_k = sparse_top_k
        self.dense_top_k = dense_top_k
        self.sparse_weight = sparse_weight
        self.dense_weight = dense_weight
        self.rrf_k = rrf_k
        self.sparse_config_json = (
            sparse_config.model_dump_json() if sparse_config is not None else None
        )

    def search(self, query: str, *, top_k: int = 10) -> list[dict]:
        """Return unique URLs ranked by RRF, with channel ranks and raw scores."""
        if top_k < 1:
            raise ValueError("top_k must be positive")
        if not query.strip():
            return []
        sparse_hits = (
            json.loads(
                self.sparse.search(
                    query,
                    top_k=self.sparse_top_k,
                    config_json=self.sparse_config_json,
                )
            )
            if self.sparse_weight > 0
            else []
        )
        dense_hits = (
            self.dense.search(query, top_k=self.dense_top_k)
            if self.dense_weight > 0
            else []
        )
        return rrf_fusion(
            sparse_hits,
            dense_hits,
            top_k=top_k,
            sparse_weight=self.sparse_weight,
            dense_weight=self.dense_weight,
            rrf_k=self.rrf_k,
        )
