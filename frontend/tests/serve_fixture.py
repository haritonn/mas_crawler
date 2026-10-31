"""Disposable synthetic corpus for browser tests; no model or live crawling."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from mas_crawler._native import build_index
from mas_crawler.benchmark.dataset import AnnotationPair, export_annotation_csv
from mas_crawler.benchmark.generation import GeneratedQuery
from mas_crawler.benchmark.workflow import AnnotationPackage

with tempfile.TemporaryDirectory(prefix="gather-browser-", dir=os.environ.get("TMPDIR")) as temp:
    root = Path(temp)
    run = root / "browser-fixture"
    run.mkdir()
    documents = [
        {"url": "https://example.test/ffi", "title": "CStr", "text": "std::ffi CStr from_bytes_until_nul constructs a C string from bytes. FromBytesUntilNulError means a nul byte is missing."},
        {"url": "https://example.test/stdin", "title": "Stdin", "text": "std::io Stdin lock read_line lines. Read a line of standard input using a locked handle."},
    ]
    corpus = run / "corpus.jsonl"
    corpus.write_text("".join(json.dumps(doc) + "\n" for doc in documents), encoding="utf-8")
    count = build_index(str(corpus), str(run / "index"))
    (run / "result.json").write_text(json.dumps({"indexed_documents": count, "index_path": str(run / "index")}), encoding="utf-8")
    queries = [GeneratedQuery(query_id="q1", query="std::ffi CStr", source_url=documents[0]["url"]), GeneratedQuery(query_id="q2", query="Stdin read_line", source_url=documents[1]["url"])]
    pairs = [AnnotationPair(pair_id=f"p{qi * 2 + di + 1}", query_id=query.query_id, query=query.query, document_url=doc["url"], document_title=doc["title"], document_text=doc["text"]) for qi, query in enumerate(queries) for di, doc in enumerate(documents)]
    package = AnnotationPackage(corpus_path=str(corpus), index_path=str(run / "index"), goal="Проверить браузерный интерфейс на синтетическом корпусе", seed=42, sample_size=2, max_pairs=4, candidates_per_query=2, max_chars=1000, queries=queries, pairs=pairs)
    annotation = run / "annotation"
    annotation.mkdir()
    (annotation / "source.json").write_text(package.model_dump_json(indent=2), encoding="utf-8")
    export_annotation_csv(pairs, annotation / "annotation.csv")
    management = root / "management-fixture"
    shutil.copytree(run, management)
    copied = package.model_copy(update={
        "corpus_path": str(management / "corpus.jsonl"),
        "index_path": str(management / "index"),
    })
    (management / "annotation/source.json").write_text(copied.model_dump_json(indent=2), encoding="utf-8")
    (management / "ui.json").write_text('{"name": "Управляемый источник"}', encoding="utf-8")
    subprocess.run([sys.executable, "-m", "mas_crawler.web.app", "--runs-dir", str(root), "--port", "8011"], check=True)
