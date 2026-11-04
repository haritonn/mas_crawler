from __future__ import annotations

import json
from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mas_crawler._native import SearchIndex
from mas_crawler.benchmark.evaluation import Qrels
from mas_crawler.benchmark.experiments import SearchConfig
from mas_crawler.benchmark.retrieval import evaluate_retriever
from mas_crawler.hybrid import rrf_fusion

if TYPE_CHECKING:
    from mas_crawler.dense import DenseSearch


class RetrievalExperiment(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(min_length=1)
    mode: Literal["bm25", "dense", "hybrid"] = "bm25"

    sparse_config: SearchConfig = Field(
        default_factory=lambda: SearchConfig(title_weight=1.0, text_weight=1.0)
    )
    sparse_top_k: int = Field(default=100, gt=0)
    dense_top_k: int = Field(default=100, gt=0)
    sparse_weight: float = Field(default=1.0, ge=0)
    dense_weight: float = Field(default=1.0, ge=0)
    rrf_k: float = Field(default=60.0, gt=0)

    @model_validator(mode="after")
    def check_weights(self) -> Self:
        if self.mode == "hybrid" and self.sparse_weight == self.dense_weight == 0:
            raise ValueError("At least one hybrid channel weight must be positive")
        return self


def _search_bm25(
    index: SearchIndex, config_json: str, query: str, *, top_k: int
) -> list[dict]:
    return json.loads(index.search(query, top_k=top_k, config_json=config_json))


def evaluate_retrieval_experiments(
    index: SearchIndex,
    queries: dict[str, str],
    qrels: Qrels,
    experiments: list[RetrievalExperiment],
    *,
    dense: DenseSearch | None = None,
    k: int = 10,
) -> list[dict[str, Any]]:
    if not experiments:
        raise ValueError("experiments must not be empty")
    names = [spec.name for spec in experiments]
    if len(set(names)) != len(names):
        raise ValueError("Experiment names must be unique")
    if dense is None and any(spec.mode != "bm25" for spec in experiments):
        raise ValueError("A dense retriever is required for dense and hybrid modes")

    sparse_cache = {}
    dense_cache = {}

    def search_sparse(config_json: str, query: str, *, top_k: int) -> list[dict]:
        key = (query, config_json, top_k)
        if key not in sparse_cache:
            sparse_cache[key] = _search_bm25(index, config_json, query, top_k=top_k)
        return sparse_cache[key]

    def search_dense(query: str, *, top_k: int) -> list[dict]:
        if dense is None:
            raise ValueError("A dense retriever is required")
        key = (query, top_k)
        if key not in dense_cache:
            dense_cache[key] = dense.search(query, top_k=top_k)
        return dense_cache[key]

    def search_hybrid(
        spec: RetrievalExperiment, query: str, *, top_k: int
    ) -> list[dict]:
        if not query.strip():
            return []
        sparse_hits = (
            search_sparse(
                spec.sparse_config.model_dump_json(), query, top_k=spec.sparse_top_k
            )
            if spec.sparse_weight > 0
            else []
        )
        dense_hits = (
            search_dense(query, top_k=spec.dense_top_k) if spec.dense_weight > 0 else []
        )
        return rrf_fusion(
            sparse_hits,
            dense_hits,
            top_k=top_k,
            sparse_weight=spec.sparse_weight,
            dense_weight=spec.dense_weight,
            rrf_k=spec.rrf_k,
        )

    reports = []
    for spec in experiments:
        search: Callable[..., list[dict]]
        if spec.mode == "bm25":
            search = partial(search_sparse, spec.sparse_config.model_dump_json())
        elif spec.mode == "dense":
            search = search_dense
        else:
            search = partial(search_hybrid, spec)

        report = evaluate_retriever(search, queries, qrels, k=k)
        report["timing"]["scope"] = "execution_with_channel_cache"
        reports.append(
            {
                "name": spec.name,
                "config": spec.model_dump(mode="json", exclude={"name"}),
                **report,
            }
        )
    return reports
