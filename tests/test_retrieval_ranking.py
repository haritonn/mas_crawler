"""Metric evaluation must preserve the saved hybrid ranking, including ties."""

import json

import pytest

from mas_crawler.benchmark.retrieval_experiments import (
    RetrievalExperiment,
    evaluate_retrieval_experiments,
)


class SparseIndex:
    def search(self, query, *, top_k, config_json):
        hits = [{"url": "https://a", "title": "A", "score": 7.0}]
        return json.dumps(hits[:top_k] if query == "query" else [])


class DenseRetriever:
    def search(self, query, *, top_k):
        hits = [{"url": "https://z", "title": "Z", "score": 0.8}]
        return hits[:top_k] if query == "query" else []


@pytest.mark.parametrize(
    ("relevance", "expected_ndcg"),
    [
        ({"https://a": 3, "https://z": 0}, 1.0),
        ({"https://a": 0, "https://z": 3}, 0.6309297535714574),
    ],
)
def test_hybrid_metrics_preserve_saved_rank_order(relevance, expected_ndcg):
    report = evaluate_retrieval_experiments(
        SparseIndex(),
        {"q1": "query", "q2": "no results"},
        {"q1": relevance, "q2": {"https://a": 3}},
        [
            RetrievalExperiment(
                name="equal-weights",
                mode="hybrid",
                sparse_top_k=1,
                dense_top_k=1,
                sparse_weight=1.0,
                dense_weight=1.0,
                rrf_k=60.0,
            )
        ],
        dense=DenseRetriever(),
        k=2,
    )[0]

    assert report["results"]["q1"] == [
        {
            "url": "https://a",
            "title": "A",
            "score": 1.0 / 61.0,
            "sparse_rank": 1,
            "dense_rank": None,
            "sparse_score": 7.0,
            "dense_score": None,
        },
        {
            "url": "https://z",
            "title": "Z",
            "score": 1.0 / 61.0,
            "sparse_rank": None,
            "dense_rank": 1,
            "sparse_score": None,
            "dense_score": 0.8,
        },
    ]
    assert report["results"]["q2"] == []
    evaluation = report["evaluation"]
    assert evaluation["per_query"]["q1"]["nDCG@2"] == pytest.approx(expected_ndcg)
    assert evaluation["per_query"]["q2"]["nDCG@2"] == 0.0
    assert evaluation["aggregate"]["nDCG@2"] == pytest.approx(expected_ndcg / 2)
