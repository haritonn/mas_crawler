"""Build a new index without modifying an existing working index."""

import hashlib
import json
from pathlib import Path

from .config import load_config


def build(config_path: Path, output: Path | None = None) -> dict:
    config = load_config(config_path)
    index_path = Path(output).resolve() if output is not None else config.index
    if index_path.exists():
        raise FileExistsError(f"Index already exists; use a new --output: {index_path}")

    from ._native import build_index

    # Fingerprint the corpus used for the build, not the caller's checkout path.
    with config.corpus.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    count = build_index(str(config.corpus), str(index_path))
    report = {
        "schema_version": 1,
        "engine": "tantivy",
        "engine_version": "0.26.2",
        "indexed_documents": count,
        "corpus_sha256": digest,
    }
    with (index_path / "build.json").open("x", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return {"index_path": str(index_path), **report}
