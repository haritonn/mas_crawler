import json

import pytest


@pytest.fixture
def project(tmp_path):
    corpus = tmp_path / "documents.jsonl"
    documents = [
        {"url": "https://example.invalid/title", "title": "quartz", "text": "ordinary"},
        {"url": "https://example.invalid/text", "title": "ordinary", "text": "quartz"},
    ]
    corpus.write_text(
        "".join(json.dumps(doc) + "\n" for doc in documents), encoding="utf-8"
    )
    config = tmp_path / "search.toml"
    config.write_text(
        '[project]\nname = "Fixture search"\n'
        '[storage]\ncorpus = "documents.jsonl"\nindex = "indexes/v1"\n'
        "[search]\ntitle_weight = 20.0\ntext_weight = 1.0\n",
        encoding="utf-8",
    )
    return config
