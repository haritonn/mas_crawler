"""Embedding model configuration, independent of execution resources."""

from typing import Literal

from pydantic import Field

from ..config import Settings


class EmbeddingProfile(Settings):
    model_id: str = Field(min_length=1)
    revision: str | None = Field(default=None, min_length=1)

    query_prompt: str | None = None
    document_prompt: str | None = None

    max_seq_length: int | None = Field(default=None, gt=0)
    similarity: Literal["cosine", "dot", "euclidean"] = "cosine"
    normalize_embeddings: bool = False
