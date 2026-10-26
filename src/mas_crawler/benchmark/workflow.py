"""Persist annotation tasks and accept human labels in a later process."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .._native import SearchIndex
from ..config import AppConfig, load_config
from .dataset import (
    AnnotationPair,
    annotations_to_benchmark,
    export_annotation_csv,
    import_annotation_csv,
    split_annotations,
    validate_annotations,
)
from .generation import (
    GeneratedQuery,
    build_annotation_pairs,
    generate_queries,
    load_corpus,
    sample_documents,
)


class AnnotationPackage(BaseModel):
    corpus_path: str
    index_path: str
    goal: str
    seed: int
    sample_size: int
    max_pairs: int
    candidates_per_query: int
    max_chars: int
    queries: list[GeneratedQuery]
    pairs: list[AnnotationPair]


def prepare_benchmark(
    corpus_path: Path,
    index_path: Path,
    goal: str,
    output_dir: Path,
    *,
    max_pairs: int = 100,
    sample_size: int | None = None,
    candidates_per_query: int = 5,
    max_chars: int = 12000,
    seed: int = 42,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """Generate a new package; only annotation.csv needs to reach the annotator."""
    if output_dir.exists():
        raise FileExistsError(f"Annotation package already exists: {output_dir}")
    if max_pairs < 4 or candidates_per_query < 2 or max_chars < 1:
        raise ValueError(
            "Need max_pairs >= 4, candidates_per_query >= 2 and max_chars > 0"
        )
    if not goal.strip():
        raise ValueError("Benchmark goal must not be blank")

    documents = load_corpus(corpus_path)
    if sample_size is None:
        sample_size = min(len(documents), max(2, max_pairs // candidates_per_query))
    if sample_size < 2 or sample_size > max_pairs // 2:
        raise ValueError("Sample needs at least two documents and two pairs per query")
    selected = sample_documents(documents, sample_size, seed=seed)
    index = SearchIndex(str(index_path))
    config = config if config is not None else load_config()
    queries = generate_queries(selected, goal, config=config, max_chars=max_chars)
    if len(queries) < 2:
        raise ValueError(
            "Generator produced fewer than two distinct queries; no package saved"
        )
    pairs = build_annotation_pairs(
        queries,
        documents,
        index,
        max_pairs=max_pairs,
        candidates_per_query=candidates_per_query,
        seed=seed,
    )
    package = AnnotationPackage(
        corpus_path=str(corpus_path.resolve()),
        index_path=str(index_path.resolve()),
        goal=goal,
        seed=seed,
        sample_size=sample_size,
        max_pairs=max_pairs,
        candidates_per_query=candidates_per_query,
        max_chars=max_chars,
        queries=queries,
        pairs=pairs,
    )

    output_dir.mkdir(parents=True, exist_ok=False)
    with (output_dir / "source.json").open("x", encoding="utf-8") as file:
        file.write(package.model_dump_json(indent=2))
    export_annotation_csv(pairs, output_dir / "annotation.csv")
    return {
        "package_dir": str(output_dir.resolve()),
        "annotation_path": str((output_dir / "annotation.csv").resolve()),
        "sampled_documents": sample_size,
        "queries": len(queries),
        "pairs": len(pairs),
        "max_pairs": max_pairs,
    }


def accept_benchmark(
    package_dir: Path,
    annotations: Path,
    *,
    test_fraction: float = 0.3,
    seed: int = 42,
) -> dict[str, Any]:
    """Check returned labels against saved tasks and freeze one dev/test split."""
    ready_dir = package_dir / "benchmark"
    if ready_dir.exists():
        raise FileExistsError(f"Benchmark already accepted; reuse {ready_dir}")

    package = AnnotationPackage.model_validate_json(
        (package_dir / "source.json").read_text(encoding="utf-8")
    )
    pairs = import_annotation_csv(annotations)
    validate_annotations(pairs)
    original = {pair.pair_id: pair for pair in package.pairs}
    returned = {pair.pair_id: pair for pair in pairs}
    if original.keys() != returned.keys():
        missing = sorted(original.keys() - returned.keys())
        unknown = sorted(returned.keys() - original.keys())
        raise ValueError(
            f"Annotation pair IDs differ: missing={missing}, unknown={unknown}"
        )
    for pair_id, pair in returned.items():
        if pair.model_dump(exclude={"relevance"}) != original[pair_id].model_dump(
            exclude={"relevance"}
        ):
            raise ValueError(f"Task fields changed for {pair_id}; edit only relevance")

    # Restore package order: CSV row order is not part of the annotation contract.
    pairs = [returned[pair.pair_id] for pair in package.pairs]
    dev, test = split_annotations(pairs, test_fraction=test_fraction, seed=seed)
    dev_queries, dev_qrels = annotations_to_benchmark(dev)
    test_queries, test_qrels = annotations_to_benchmark(test)
    split = {
        "corpus_path": package.corpus_path,
        "index_path": package.index_path,
        "label_source": "human",
        "seed": seed,
        "test_fraction": test_fraction,
        "pairs": len(pairs),
        "dev_pairs": len(dev),
        "test_pairs": len(test),
        "dev_query_ids": sorted(dev_queries),
        "test_query_ids": sorted(test_queries),
    }

    # Validate everything before creating output; split.json is written last.
    ready_dir.mkdir(exist_ok=False)
    export_annotation_csv(dev, ready_dir / "dev.csv")
    export_annotation_csv(test, ready_dir / "test.csv")
    for name, data in [
        ("dev.json", {"queries": dev_queries, "qrels": dev_qrels}),
        ("test.json", {"queries": test_queries, "qrels": test_qrels}),
        ("split.json", split),
    ]:
        with (ready_dir / name).open("x", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
    return {
        "benchmark_dir": str(ready_dir.resolve()),
        "dev_path": str((ready_dir / "dev.json").resolve()),
        "test_path": str((ready_dir / "test.json").resolve()),
        "pairs": len(pairs),
        "dev_queries": len(dev_queries),
        "test_queries": len(test_queries),
    }
