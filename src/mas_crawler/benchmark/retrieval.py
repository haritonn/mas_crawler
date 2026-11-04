from collections.abc import Callable
from time import perf_counter
from typing import Any

from mas_crawler.benchmark.evaluation import Qrels, Run, evaluate_run


def evaluate_retriever(
    search: Callable[..., list[dict]],
    queries: dict[str, str],
    qrels: Qrels,
    *,
    k: int = 10,
) -> dict[str, Any]:
    """Measure search calls only; backend initialization happens outside."""
    if queries.keys() != qrels.keys():
        raise ValueError("queries and qrels must have identical query IDs")
    if any(not judgments for judgments in qrels.values()):
        raise ValueError("Each query needs at least one relevance judgment")

    results: dict[str, list[dict]] = {}
    run: Run = {}
    per_query_seconds: dict[str, float] = {}

    for query_id, query in queries.items():
        started = perf_counter()
        hits = search(query, top_k=k)
        per_query_seconds[query_id] = perf_counter() - started
        hits = hits[:k]

        # Preserve the supplied ranking even when backend scores are tied.
        scores = {hit["url"]: -float(rank) for rank, hit in enumerate(hits, start=1)}
        if len(scores) != len(hits):
            raise ValueError(f"Duplicate result URLs for query {query_id}")
        results[query_id] = hits
        run[query_id] = scores

    return {
        "queries": queries.copy(),
        "results": results,
        "evaluation": evaluate_run(qrels, run, k),
        "timing": {
            "search_seconds": sum(per_query_seconds.values()),
            "per_query_seconds": per_query_seconds,
        },
    }
