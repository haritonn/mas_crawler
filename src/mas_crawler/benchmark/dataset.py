"""Whole work with CSV annotations"""

import csv
from math import ceil
from pathlib import Path
from random import Random

from pydantic import BaseModel, ConfigDict, Field

from .evaluation import Qrels


class AnnotationPair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pair_id: str
    query_id: str
    query: str
    document_url: str
    document_title: str
    document_text: str
    relevance: int | None = Field(default=None, ge=0, le=3, strict=True)


def export_annotation_csv(pairs: list[AnnotationPair], output: Path) -> None:
    fieldnames = [
        "pair_id",
        "query_id",
        "query",
        "document_url",
        "document_title",
        "document_text",
        "relevance",
    ]
    with output.open("x", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for pair in pairs:
            writer.writerow(pair.model_dump())


def import_annotation_csv(source: Path) -> list[AnnotationPair]:
    pairs = []

    with source.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames or []
        if len(columns) != len(set(columns)) or set(columns) != set(
            AnnotationPair.model_fields
        ):
            raise ValueError("CSV columns do not match AnnotationPair")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Malformed CSV record near line {reader.line_num}")
            try:
                grade = row["relevance"].strip()
                row["relevance"] = int(grade) if grade else None

                pairs.append(AnnotationPair.model_validate(row))
            except ValueError as error:
                raise ValueError(
                    f"Invalid annotation near line {reader.line_num}: {error}"
                ) from error

    return pairs


def validate_annotations(pairs: list[AnnotationPair]) -> None:
    if not pairs:
        raise ValueError("Annotation dataset is empty")

    pair_ids: set[str] = set()
    query_documents: set[tuple[str, str]] = set()
    queries = {}
    query_ids = {}

    for pair in pairs:
        required_values = (
            pair.pair_id,
            pair.query_id,
            pair.query,
            pair.document_url,
        )
        if not all(value.strip() for value in required_values):
            raise ValueError(
                f"Empty identifier, query or URL for pair {pair.pair_id!r}"
            )

        if pair.relevance is None:
            raise ValueError(f"Missing relevance for pair {pair.pair_id}")

        if pair.pair_id in pair_ids:
            raise ValueError(f"Duplicate pair_id: {pair.pair_id}")

        key = (pair.query_id, pair.document_url)
        if key in query_documents:
            raise ValueError(f"Duplicate query-document pair: {key}")

        if pair.query_id in queries and queries[pair.query_id] != pair.query:
            raise ValueError(f"Conflicting query text for {pair.query_id}")

        if pair.query in query_ids and query_ids[pair.query] != pair.query_id:
            raise ValueError("Identical query text has different query IDs")

        pair_ids.add(pair.pair_id)
        query_documents.add(key)
        queries[pair.query_id] = pair.query
        query_ids[pair.query] = pair.query_id


def split_annotations(
    pairs: list[AnnotationPair], *, test_fraction: float = 0.3, seed: int = 42
) -> tuple[list[AnnotationPair], list[AnnotationPair]]:
    validate_annotations(pairs)
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be between 0 and 1")

    query_ids = sorted({pair.query_id for pair in pairs})
    if len(query_ids) < 2:
        raise ValueError("At least two distinct queries are required")

    Random(seed).shuffle(query_ids)
    query_len = len(query_ids)
    test_count = min(query_len - 1, ceil(query_len * test_fraction))
    test_ids = set(query_ids[:test_count])

    dev, test = [], []
    for pair in pairs:
        if pair.query_id in test_ids:
            test.append(pair)
        else:
            dev.append(pair)

    return dev, test


def annotations_to_benchmark(
    pairs: list[AnnotationPair],
) -> tuple[dict[str, str], Qrels]:
    validate_annotations(pairs)
    queries = {}
    qrels: Qrels = {}
    for pair in pairs:
        assert pair.relevance is not None
        queries[pair.query_id] = pair.query
        qrels.setdefault(pair.query_id, {})[pair.document_url] = pair.relevance

    return queries, qrels
