"""Read project-local configuration; relative paths belong to its directory."""

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SearchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    title_weight: float = Field(default=1.0, ge=0)
    text_weight: float = Field(default=1.0, ge=0)

    @model_validator(mode="after")
    def positive_weight(self):
        if self.title_weight == 0 and self.text_weight == 0:
            raise ValueError("At least one search weight must be positive")
        return self


class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="Search service", min_length=1)


class StorageSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus: Path = Path("data/documents.jsonl")
    index: Path = Path("indexes/lexical")


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    project: ProjectSettings = Field(default_factory=ProjectSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)

    @property
    def name(self) -> str:
        return self.project.name

    @property
    def corpus(self) -> Path:
        return self.storage.corpus

    @property
    def index(self) -> Path:
        return self.storage.index


def load_config(path: Path) -> ProjectConfig:
    path = Path(path).resolve()
    with path.open("rb") as file:
        config = ProjectConfig.model_validate(tomllib.load(file))
    config.storage.corpus = (path.parent / config.corpus).resolve()
    config.storage.index = (path.parent / config.index).resolve()
    return config
