"""Build and read reusable dense-index artifacts."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from itertools import batched
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import numpy as np

from ..benchmark.generation import load_corpus
from .chunking import split_text
from .config import EmbeddingProfile
from .embeddings import TextEmbedder


def iter_chunks(directory: Path):
    with (directory / "chunks.jsonl").open(encoding="utf-8") as file:
        for line in file:
            yield json.loads(line)


def read_build(directory: Path) -> dict:
    with (directory / "build.json").open(encoding="utf-8") as file:
        report = json.load(file)
    if report["schema_version"] != 1:
        raise ValueError("Unsupported dense build schema")
    return report


def build_dense(
    corpus_path: Path,
    output_dir: Path,
    profile: EmbeddingProfile,
    *,
    chunk_size: int = 192,
    overlap: int = 32,
    batch_size: int = 32,
    device: str | None = None,
    progress: Callable[[str, int, int | None], None] | None = None,
) -> dict:
    if batch_size < 1 or chunk_size < 1 or not 0 <= overlap < chunk_size:
        raise ValueError("Invalid batch_size, chunk_size or overlap")
    output_dir.mkdir(parents=True, exist_ok=False)
    if progress is not None:
        progress("model", 0, None)
    print("Loading embedding model", flush=True)
    embedder = TextEmbedder(profile, device=device)
    with corpus_path.open("rb") as file:
        source_sha256 = hashlib.file_digest(file, "sha256").hexdigest()
    documents = load_corpus(corpus_path)
    with corpus_path.open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != source_sha256:
            raise ValueError("Corpus changed while being loaded")

    build_id = uuid4().hex
    budget = embedder.max_length - embedder.input_length("", "document")
    effective_size = min(chunk_size, budget)
    if effective_size <= overlap:
        raise ValueError("Model/prompt token budget is too small for overlap")
    count = 0
    if progress is not None:
        progress("chunking", 0, len(documents))
    with (output_dir / "chunks.jsonl").open("x", encoding="utf-8") as file:
        for document_number, document in enumerate(documents, start=1):
            chunks = split_text(
                document.text,
                embedder.model.tokenizer,
                chunk_size=effective_size,
                overlap=overlap,
            )
            for chunk in chunks:
                length = embedder.input_length(chunk.text, "document")
                if length > embedder.max_length:
                    raise ValueError(
                        f"Oversized fragment at {document.url}, chunk {chunk.position}; "
                        "reduce chunk_size"
                    )
                identity = json.dumps([build_id, document.url, chunk.position])
                record = {
                    "id": str(uuid5(NAMESPACE_URL, identity)),
                    "url": document.url,
                    "title": document.title,
                    **asdict(chunk),
                }
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
            if progress is not None:
                progress("chunking", document_number, len(documents))
    if count == 0:
        raise ValueError("Corpus produced no chunks")
    dimension = embedder.model.get_embedding_dimension()
    if dimension is None or dimension < 1:
        raise ValueError("Model has no fixed embedding dimension")
    vectors = np.lib.format.open_memmap(
        output_dir / "embeddings.npy",
        mode="w+",
        dtype=np.float32,
        shape=(count, dimension),
    )
    offset = 0
    print(f"Encoding {count} chunks; effective window={effective_size}", flush=True)
    if progress is not None:
        progress("encoding", 0, count)
    for batch in batched(iter_chunks(output_dir), batch_size):
        encoded = embedder.encode_documents(
            [record["text"] for record in batch], batch_size=batch_size
        )
        if encoded.shape != (len(batch), dimension) or not np.isfinite(encoded).all():
            raise ValueError("Invalid embedding batch")
        vectors[offset : offset + len(batch)] = encoded
        offset += len(batch)
        vectors.flush()
        if progress is not None:
            progress("encoding", offset, count)
        print(f"Encoded {offset}/{count}", flush=True)
    del vectors
    if offset != count:
        raise ValueError("Chunk count changed during encoding")
    embedder.model.save_pretrained(str(output_dir / "model"))
    report = {
        "schema_version": 1,
        "build_id": build_id,
        "collection": f"dense_{build_id}",
        "source_sha256": source_sha256,
        "documents": len(documents),
        "chunks": count,
        "dimension": dimension,
        "profile": embedder.profile.model_dump(),
        "document_format": "text_only",
        "chunk_size": effective_size,
        "requested_chunk_size": chunk_size,
        "overlap": overlap,
    }
    with (output_dir / "build.json").open("x", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    return report
