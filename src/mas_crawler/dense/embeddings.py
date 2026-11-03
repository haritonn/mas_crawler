from typing import Literal

import numpy as np
from sentence_transformers import SentenceTransformer
from sentence_transformers.base.modules import Transformer

from .config import EmbeddingProfile


class TextEmbedder:
    def __init__(self, profile: EmbeddingProfile, *, device: str | None = None) -> None:
        self.profile = profile.model_copy(deep=True)
        self.model = SentenceTransformer(
            profile.model_id,
            revision=profile.revision,
            device=device,
            trust_remote_code=False,
            similarity_fn_name=profile.similarity,
        )
        # The initial catalog supports the ordinary Transformer input pipeline.
        first = self.model[0]
        if not isinstance(first, Transformer) or first.query_expansion is not None:
            raise ValueError(
                "This MVP requires a Transformer input module without query expansion"
            )
        if self.model.tokenizer is None or not self.model.tokenizer.is_fast:
            raise ValueError("This MVP requires a fast tokenizer")
        limit = self.model.max_seq_length
        if limit is None or limit < 1:
            raise ValueError("The model must declare a finite max_seq_length")
        if profile.max_seq_length is not None:
            if profile.max_seq_length > limit:
                raise ValueError(
                    "max_seq_length cannot exceed the model's declared limit"
                )
            limit = profile.max_seq_length
        self.max_length = limit
        self.model.max_seq_length = limit
        self.profile.max_seq_length = limit
        self.profile.query_prompt = self._resolve_prompt(
            profile.query_prompt, ["query"]
        )
        self.profile.document_prompt = self._resolve_prompt(
            profile.document_prompt, ["document", "passage", "corpus"]
        )

    def _resolve_prompt(self, override: str | None, names: list[str]) -> str:
        if override is not None:
            return override
        for name in [*names, self.model.default_prompt_name]:
            if name is not None and name in self.model.prompts:
                return self.model.prompts[name]
        return ""

    def input_length(self, text: str, task: Literal["query", "document"]) -> int:
        prompt = (
            self.profile.query_prompt
            if task == "query"
            else self.profile.document_prompt
        )
        features = self.model.preprocess(
            [text],
            prompt=prompt,
            task=task,
            processing_kwargs={"text": {"truncation": False, "padding": False}},
        )
        return int(features["input_ids"].shape[-1])

    def _check_lengths(
        self, texts: list[str], task: Literal["query", "document"]
    ) -> None:
        for position, text in enumerate(texts):
            length = self.input_length(text, task)
            if length > self.max_length:
                raise ValueError(
                    f"{task} input {position}: {length} tokens exceed {self.max_length}; "
                    "reduce chunk_size or shorten the query/prompt"
                )

    def encode_documents(self, texts: list[str], *, batch_size: int = 32) -> np.ndarray:
        if not texts or batch_size < 1:
            raise ValueError("Provide nonempty texts and a positive batch_size")
        self._check_lengths(texts, "document")
        return self.model.encode_document(
            texts,
            prompt=self.profile.document_prompt,
            batch_size=batch_size,
            normalize_embeddings=self.profile.normalize_embeddings,
            convert_to_numpy=True,
            show_progress_bar=False,
            processing_kwargs={
                "text": {"truncation": False, "max_length": self.max_length}
            },
        )

    def encode_query(self, text: str) -> np.ndarray:
        if not text.strip():
            raise ValueError("Query must not be blank")
        self._check_lengths([text], "query")
        return self.model.encode_query(
            text,
            prompt=self.profile.query_prompt,
            normalize_embeddings=self.profile.normalize_embeddings,
            convert_to_numpy=True,
            show_progress_bar=False,
            processing_kwargs={
                "text": {"truncation": False, "max_length": self.max_length}
            },
        )
