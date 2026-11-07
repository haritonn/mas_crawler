"""Upload saved embeddings to Qdrant and serve document-level search."""

from collections.abc import Callable
from itertools import batched
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient, models

from .build import iter_chunks, read_build
from .config import EmbeddingProfile
from .embeddings import TextEmbedder

DISTANCES = {
    "cosine": models.Distance.COSINE,
    "dot": models.Distance.DOT,
    "euclidean": models.Distance.EUCLID,
}


def upload_dense(
    directory: Path,
    client: QdrantClient,
    *,
    batch_size: int = 128,
    progress: Callable[[str, int, int | None], None] | None = None,
) -> dict:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    report = read_build(directory)
    vectors = np.load(directory / "embeddings.npy", mmap_mode="r", allow_pickle=False)
    if vectors.shape != (report["chunks"], report["dimension"]):
        raise ValueError("Embedding matrix does not match build.json")
    name = report["collection"]
    distance = DISTANCES[report["profile"]["similarity"]]
    if progress is not None:
        progress("upload", 0, report["chunks"])
    if not client.collection_exists(name):
        client.create_collection(
            name,
            vectors_config=models.VectorParams(
                size=report["dimension"], distance=distance
            ),
            metadata={"build_id": report["build_id"], "ready": False},
        )
        client.create_payload_index(
            name, "url", models.PayloadSchemaType.KEYWORD, wait=True
        )
    info = client.get_collection(name)
    if (
        (info.config.metadata or {}).get("build_id") != report["build_id"]
        or info.config.params.vectors.size != report["dimension"]
        or info.config.params.vectors.distance != distance
    ):
        raise ValueError("Collection belongs to another embedding build")
    offset = 0
    for batch in batched(iter_chunks(directory), batch_size):
        if offset + len(batch) > len(vectors):
            raise ValueError("More chunk records than embedding rows")
        values = vectors[offset : offset + len(batch)]
        if not np.isfinite(values).all():
            raise ValueError("Nonfinite stored embeddings")
        points = [
            models.PointStruct(id=record["id"], vector=vector.tolist(), payload=record)
            for record, vector in zip(batch, values, strict=True)
        ]
        client.upsert(name, points=points, wait=True)
        offset += len(batch)
        if progress is not None:
            progress("upload", offset, report["chunks"])
        print(f"Uploaded {offset}/{report['chunks']}", flush=True)
    if offset != report["chunks"] or client.count(name, exact=True).count != offset:
        raise ValueError("Qdrant point count does not match the embedding build")
    client.update_collection(
        name, metadata={"build_id": report["build_id"], "ready": True}
    )
    if not (client.get_collection(name).config.metadata or {}).get("ready"):
        raise RuntimeError("Qdrant collection was not marked ready")
    return {"collection": name, "points": offset}


class DenseSearch:
    def __init__(
        self, directory: Path, client: QdrantClient, *, device: str | None = None
    ) -> None:
        self.report = read_build(directory)
        self.client = client
        info = client.get_collection(self.report["collection"])
        metadata = info.config.metadata or {}
        if metadata.get("build_id") != self.report["build_id"] or not metadata.get(
            "ready"
        ):
            raise ValueError("Collection is incomplete or belongs to another build")
        if (
            client.count(self.report["collection"], exact=True).count
            != self.report["chunks"]
        ):
            raise ValueError("Collection point count differs from the completed build")
        profile = EmbeddingProfile.model_validate(self.report["profile"])
        profile.model_id = str(directory.resolve() / "model")
        profile.revision = None
        if (
            info.config.params.vectors.size != self.report["dimension"]
            or info.config.params.vectors.distance != DISTANCES[profile.similarity]
        ):
            raise ValueError("Collection vector configuration differs from the build")
        self.embedder = TextEmbedder(profile, device=device)
        if self.embedder.model.get_embedding_dimension() != self.report["dimension"]:
            raise ValueError("Saved model dimension differs from the index")

    def search(self, query: str, *, top_k: int = 10) -> list[dict]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        vector = self.embedder.encode_query(query)
        result = self.client.query_points_groups(
            collection_name=self.report["collection"],
            query=vector.tolist(),
            group_by="url",
            group_size=1,
            limit=top_k,
            with_payload=True,
        )
        hits = []
        for group in result.groups:
            hit = group.hits[0]
            payload = hit.payload
            score = (
                -hit.score
                if self.report["profile"]["similarity"] == "euclidean"
                else hit.score
            )
            hits.append(
                {
                    "url": payload["url"],
                    "title": payload["title"],
                    "score": score,
                    "text": payload["text"],
                    "chunk_position": payload["position"],
                }
            )
        return hits
