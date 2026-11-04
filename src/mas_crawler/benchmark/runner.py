"""Load benchmark inputs, reuse open search engines, and persist evaluation."""

import json
from contextlib import ExitStack, closing
from pathlib import Path
from typing import Any

from .._native import SearchIndex
from .retrieval_experiments import RetrievalExperiment, evaluate_retrieval_experiments


def evaluate_benchmark(
    dataset_path: Path,
    index_path: Path,
    experiments_path: Path,
    output_path: Path,
    *,
    dense_build: Path | None = None,
    qdrant_url: str = "http://127.0.0.1:6333",
    device: str = "cpu",
    top_k: int = 10,
) -> dict[str, Any]:
    if output_path.exists():
        raise ValueError(f"{output_path} already exists; choose another --output")
    experiments = [
        RetrievalExperiment.model_validate(value)
        for value in json.loads(experiments_path.read_text(encoding="utf-8"))
    ]
    needs_dense = any(spec.mode != "bm25" for spec in experiments)
    if needs_dense and dense_build is None:
        raise ValueError("--dense-build is required for dense and hybrid experiments")
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    index = SearchIndex(str(index_path))
    with ExitStack() as stack:
        dense = None
        if needs_dense and dense_build is not None:
            # BM25-only evaluation needs neither the embedding stack nor Qdrant.
            from qdrant_client import QdrantClient

            from ..dense import DenseSearch

            client = stack.enter_context(
                closing(QdrantClient(url=qdrant_url, timeout=60))
            )
            dense = DenseSearch(dense_build, client, device=device)
        experiments_report = evaluate_retrieval_experiments(
            index,
            dataset["queries"],
            dataset["qrels"],
            experiments,
            dense=dense,
            k=top_k,
        )
    report = {
        "dataset": str(dataset_path.resolve()),
        "index": str(index_path.resolve()),
        "dense_build": (
            str(dense_build.resolve())
            if needs_dense and dense_build is not None
            else None
        ),
        "qdrant_url": qdrant_url if needs_dense else None,
        "top_k": top_k,
        "experiments": experiments_report,
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as file:
        file.write(serialized + "\n")
    return report
