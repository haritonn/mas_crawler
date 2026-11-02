"""Application-owned search composition; add future retrieval stages here."""

import json

from .config import ProjectConfig


class SearchBackend:
    def __init__(self, config: ProjectConfig):
        if not config.index.is_dir():
            raise FileNotFoundError(f"Build an index before serving: {config.index}")
        from ._native import SearchIndex

        self.index = SearchIndex(str(config.index))
        self.config = config

    def search(self, query: str, top_k: int) -> list[dict]:
        hits = json.loads(
            self.index.search(
                query,
                top_k,
                title_weight=self.config.search.title_weight,
                text_weight=self.config.search.text_weight,
            )
        )
        return [{"id": hit["url"], **hit} for hit in hits]
