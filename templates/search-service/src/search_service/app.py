"""Search-only HTTP application, independent of Gather and its management API."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import load_config
from .search import SearchBackend


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=10, ge=1, le=100, strict=True)

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Query must not be blank")
        return value


class SearchHit(BaseModel):
    id: str
    url: str
    title: str
    score: float


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]


def create_app(config_path: Path = Path("search.toml")) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = load_config(config_path)
        app.state.backend = SearchBackend(config)
        yield
        del app.state.backend

    app = FastAPI(title="Search service", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "project": app.state.backend.config.name}

    @app.post("/search", response_model=SearchResponse)
    def search(request: SearchRequest) -> SearchResponse:
        hits = app.state.backend.search(request.query, request.top_k)
        return SearchResponse(query=request.query, hits=hits)

    return app
