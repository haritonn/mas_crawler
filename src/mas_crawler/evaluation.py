from typing import Any

import ir_measures as ir

Qrels = dict[str, dict[str, int]]
Run = dict[str, dict[str, float]]


def evaluate_run(qrels: Qrels, run: Run, k: int = 10) -> dict[str, Any]:
    """Evaluate a search run against human judgements"""
    if k < 1:
        raise ValueError("Top-k can't be less than 1")
    run = {query_id: hits for query_id, hits in run.items() if hits}
    measures = [
        ir.nDCG @ k,
        ir.P(rel=2) @ k,
        ir.R(rel=2) @ k,
        ir.Judged @ k,
    ]
    results = ir.calc(measures, qrels, run)
    per_query = {}
    for metric in results.per_query:
        per_query.setdefault(metric.query_id, {})[str(metric.measure)] = metric.value

    return {
        "aggregate": {
            str(measure): value for measure, value in results.aggregated.items()
        },
        "per_query": per_query,
    }
