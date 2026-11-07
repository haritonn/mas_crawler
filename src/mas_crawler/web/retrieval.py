"""Run-bound retrieval resources and durable background operations.

Model dependencies are deliberately imported only when dense work is requested.
"""

import fcntl
import hashlib
import json
import re
import subprocess
import sys
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Literal
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .._native import SearchIndex
from ..benchmark.retrieval_experiments import RetrievalExperiment
from ..hybrid import rrf_fusion
from .processes import process_start, worker_alive
from .store import IDENTIFIER, Store, atomic_json, confined, read_json


class DenseProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=200)
    normalize_embeddings: bool = False
    query_prompt: str | None = Field(default=None, max_length=4000)
    document_prompt: str | None = Field(default=None, max_length=4000)
    max_seq_length: int | None = Field(default=None, gt=0)
    similarity: Literal["cosine", "dot", "euclidean"] = "cosine"

    @field_validator("model_id")
    @classmethod
    def hub_model(cls, value):
        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]*(/[A-Za-z0-9][A-Za-z0-9_.-]*)?", value
        ):
            raise ValueError("Use a Hugging Face model ID, not a filesystem path")
        return value


class DenseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: DenseProfile
    device: Literal["cpu", "cuda", "mps"] = "cpu"
    chunk_size: int = Field(default=192, ge=1, le=32768, strict=True)
    overlap: int = Field(default=32, ge=0, strict=True)
    batch_size: int = Field(default=32, ge=1, le=4096, strict=True)

    @model_validator(mode="after")
    def valid_overlap(self):
        if self.overlap >= self.chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        return self


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    top_k: int = Field(default=5, ge=1, le=100, strict=True)
    experiments: list[RetrievalExperiment] = Field(min_length=1, max_length=30)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=100, strict=True)
    config: RetrievalExperiment


def safe_tree(path: Path):
    if path.is_symlink() or (
        path.is_dir() and any(p.is_symlink() for p in path.rglob("*"))
    ):
        raise HTTPException(409, "Symlinked retrieval artifacts are not supported")


def corpus_identity(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


class Resources:
    def __init__(self, root: Path, identity: tuple):
        self.identity = identity
        index = confined(root, "index")
        if not index.is_dir():
            raise HTTPException(409, "Search index is not ready")
        safe_tree(index)
        self.index = SearchIndex(str(index))
        self.documents = {}
        with confined(root, "corpus.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    item = json.loads(line)
                    self.documents[item["url"]] = item
        self.dense = None
        self.client = None

    def close(self):
        if self.client is not None:
            self.client.close()
        self.dense = None
        self.client = None

    def enrich(self, hits):
        return [
            {
                **hit,
                "text": hit.get("text")
                or self.documents.get(hit["url"], {}).get("text", "")[:1200],
            }
            for hit in hits
        ]


def open_dense(directory, url, *, device):
    from qdrant_client import QdrantClient

    from ..dense import DenseSearch

    client = QdrantClient(url=url, timeout=5)
    try:
        return DenseSearch(directory, client, device=device), client
    except Exception:
        client.close()
        raise


class RetrievalService:
    def __init__(self, store: Store, qdrant_url: str):
        self.store = store
        self.qdrant_url = qdrant_url
        self.resources: dict[str, Resources] = {}
        self.lock = threading.RLock()
        self.workers = {}
        self._qdrant_check = None
        self._collection_checks = {}
        self._corpus_hashes = {}

    def identity(self, corpus):
        stat = corpus.stat()
        signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        cached = self._corpus_hashes.get(corpus)
        if cached is None or cached[0] != signature:
            cached = (signature, corpus_identity(corpus))
            self._corpus_hashes[corpus] = cached
        return cached[1]

    def qdrant_status(self):
        now = monotonic()
        if self._qdrant_check is not None and now - self._qdrant_check[0] < 2:
            return self._qdrant_check[1]
        try:
            with urlopen(
                self.qdrant_url.rstrip("/") + "/collections", timeout=1
            ) as response:
                data = json.load(response)
            if not isinstance(data.get("result", {}).get("collections"), list):
                raise TypeError("Not a Qdrant response")
            result = {"available": True, "error": None}
        except (OSError, ValueError, TypeError, AttributeError):
            result = {
                "available": False,
                "error": "Configured Qdrant service is unavailable.",
            }
        self._qdrant_check = (now, result)
        return result

    def collection_status(self, run_id, report):
        """Validate the active immutable build without loading model dependencies."""
        service = self.qdrant_status()
        if not service["available"]:
            return 503, service["error"]
        key = (
            self.qdrant_url,
            report.get("collection"),
            report.get("build_id"),
            report.get("source_sha256"),
            report.get("chunks"),
        )
        now = monotonic()
        cached = self._collection_checks.get(run_id)
        if cached is not None and cached[0] == key and now - cached[1] < 2:
            return cached[2]
        result = (409, "Active Qdrant collection is missing, incomplete or mismatched.")
        try:
            name = report["collection"]
            if not isinstance(name, str) or not name:
                raise ValueError("Missing collection name")
            url = self.qdrant_url.rstrip("/") + "/collections/" + quote(name, safe="")
            with urlopen(url, timeout=1) as response:
                info = json.load(response)["result"]
            metadata = info["config"]["metadata"]
            if (
                metadata.get("build_id") == report["build_id"]
                and metadata.get("ready") is True
            ):
                request = Request(
                    url + "/points/count",
                    data=b'{"exact":true}',
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request, timeout=1) as response:
                    count = json.load(response)["result"]["count"]
                if type(count) is int and count == report["chunks"]:
                    result = (200, None)
        except HTTPError:
            # A collection-specific failure does not make /collections unavailable.
            pass
        except OSError:
            result = (503, "Configured Qdrant service is unavailable.")
        except (KeyError, ValueError, TypeError, AttributeError):
            pass
        if result[0] == 503:
            self._qdrant_check = (now, {"available": False, "error": result[1]})
        self._collection_checks[run_id] = (key, now, result)
        return result

    def ready_build(self, run_id):
        ready = read_json(confined(self.directory(run_id), "ready.json"))
        if not ready or ready.get("qdrant_url") != self.qdrant_url:
            return None
        corpus = confined(self.store.artifacts(run_id), "corpus.jsonl")
        if not corpus.is_file() or self.identity(corpus) != ready.get("source_sha256"):
            self.invalidate(run_id)
            return None
        if not IDENTIFIER.fullmatch(ready["job_id"]):
            raise HTTPException(409, "Invalid dense build")
        directory = confined(self.directory(run_id), "jobs", ready["job_id"], "build")
        report = read_json(confined(directory, "build.json"))
        if report.get("build_id") != ready.get("build_id") or report.get(
            "source_sha256"
        ) != ready.get("source_sha256"):
            return None
        return directory, report

    def status(self, run_id):
        with self.operation_lock(run_id):
            jobs = self.jobs(run_id)
            job = next((j for j in jobs if j["kind"] == "dense"), None)
            ready = self.ready_build(run_id)
            report = ready[1] if ready else {}
            code, error = (
                self.collection_status(run_id, report) if ready else (409, None)
            )
            return {
                "dense": {
                    "status": job["status"] if job else "absent",
                    "ready": code == 200,
                    "error": error,
                    "job": job,
                    "profile": report.get("profile"),
                    "documents": report.get("documents", 0),
                    "chunks": report.get("chunks", 0),
                    "build_id": report.get("build_id"),
                },
                "qdrant": self.qdrant_status(),
                "active_job": next((j for j in jobs if j["status"] == "running"), None),
            }

    def prepare(self, run_id, body):
        with self.operation_lock(run_id):
            self.require_idle(run_id)
            if not self.qdrant_status()["available"]:
                raise HTTPException(503, "Configured Qdrant service is unavailable")
            return self.launch(run_id, "dense", body.model_dump(mode="json"))

    def dense_resource(self, run_id, resource):
        ready = self.ready_build(run_id)
        if ready is None:
            raise HTTPException(
                409, "Prepare a dense build for the current corpus first"
            )
        directory, report = ready
        code, error = self.collection_status(run_id, report)
        if code != 200:
            raise HTTPException(code, error)
        if (
            resource.dense is None
            or resource.dense.report["build_id"] != report["build_id"]
        ):
            resource.close()
            safe_tree(directory)
            request = DenseRequest.model_validate(
                read_json(confined(directory.parent, "request.json"))
            )
            resource.dense, resource.client = open_dense(
                directory, self.qdrant_url, device=request.device
            )
        return resource.dense

    def directory(self, run_id):
        directory = confined(self.store.run_dir(run_id), "retrieval")
        directory.mkdir(exist_ok=True)
        return directory

    @contextmanager
    def operation_lock(self, run_id):
        with self.lock:
            path = confined(self.directory(run_id), "operation.lock")
            with path.open("a") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def jobs(self, run_id):
        directory = confined(self.directory(run_id), "jobs")
        directory.mkdir(exist_ok=True)
        jobs = []
        for child in directory.iterdir():
            if (
                child.is_symlink()
                or not child.is_dir()
                or not IDENTIFIER.fullmatch(child.name)
            ):
                continue
            path = confined(child, "job.json")
            job = read_json(path)
            process = self.workers.get(job.get("id"))
            if process is not None and process.poll() is not None:
                del self.workers[job["id"]]
            if job.get("status") == "running" and not worker_alive(job):
                job.update(
                    status="interrupted",
                    error="Retrieval worker stopped before completion.",
                )
                atomic_json(path, job)
            if job:
                jobs.append(job)
        return sorted(jobs, key=lambda job: job["created_at"], reverse=True)

    def active_job(self, run_id):
        return next(
            (job for job in self.jobs(run_id) if job["status"] == "running"), None
        )

    def require_idle(self, run_id):
        if self.active_job(run_id):
            raise HTTPException(409, "A retrieval job is active for this run")
        metadata = read_json(confined(self.store.run_dir(run_id), "status.json"))
        if metadata.get("status") == "running" or worker_alive(metadata):
            raise HTTPException(409, "A dataset worker is active for this run")

    def launch(self, run_id, kind, request, *, package=None):
        # Caller holds operation_lock through validation and process publication.
        self.require_idle(run_id)
        root = self.store.artifacts(run_id)
        corpus = confined(root, "corpus.jsonl")
        if not corpus.is_file():
            raise HTTPException(409, "Corpus is not available")
        job_id = uuid4().hex
        directory = confined(self.directory(run_id), "jobs", job_id)
        directory.mkdir(parents=True)
        job = {
            "id": job_id,
            "kind": kind,
            "status": "running",
            "stage": "queued",
            "completed": 0,
            "total": None,
            "created_at": datetime.now(UTC).isoformat(),
            "error": None,
            "corpus_sha256": corpus_identity(corpus),
        }
        if package is not None:
            job.update(package=package, top_k=request["top_k"])
        atomic_json(confined(directory, "request.json"), request)
        atomic_json(confined(directory, "job.json"), job)
        try:
            with confined(directory, "worker.log").open("xb") as logfile:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "mas_crawler.web.retrieval_worker",
                        "--runs-dir",
                        str(self.store.root),
                        "--run-id",
                        run_id,
                        "--job-id",
                        job_id,
                        "--qdrant-url",
                        self.qdrant_url,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=logfile,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            job.update(
                worker_pid=process.pid, worker_started=process_start(process.pid)
            )
            self.workers[job_id] = process
            atomic_json(confined(directory, "job.json"), job)
        except OSError:
            job.update(status="failed", error="Unable to launch retrieval worker.")
            atomic_json(confined(directory, "job.json"), job)
            raise HTTPException(503, job["error"]) from None
        return job

    def evaluate(self, run_id, package, body):
        with self.operation_lock(run_id):
            directory = self.store.package(run_id, package)
            if not self.store.accepted(directory):
                raise HTTPException(409, "Accept labels before evaluating")
            names = [spec.name for spec in body.experiments]
            if len(names) != len(set(names)):
                raise HTTPException(422, "Experiment names must be unique")
            self.resource(run_id)
            if (
                any(spec.mode != "bm25" for spec in body.experiments)
                and self.ready_build(run_id) is None
            ):
                raise HTTPException(409, "Prepare a dense build before evaluating")
            return self.launch(
                run_id, "evaluation", body.model_dump(mode="json"), package=package
            )

    def history(self, run_id, package):
        self.store.package(run_id, package)
        with self.operation_lock(run_id):
            jobs = self.jobs(run_id)
            return {
                "evaluations": [
                    j
                    for j in jobs
                    if j["kind"] == "evaluation" and j.get("package") == package
                ],
                "active_job": next((j for j in jobs if j["status"] == "running"), None),
            }

    def detail(self, run_id, package, job_id):
        self.store.package(run_id, package)
        with self.operation_lock(run_id):
            job = next(
                (
                    j
                    for j in self.jobs(run_id)
                    if j["id"] == job_id
                    and j["kind"] == "evaluation"
                    and j.get("package") == package
                ),
                None,
            )
            if job is None:
                raise HTTPException(404, "Evaluation not found")
            report = (
                read_json(
                    confined(self.directory(run_id), "jobs", job["id"], "report.json")
                )
                if job["status"] == "ready"
                else None
            )
            return {"job": job, "report": report}

    def invalidate(self, run_id):
        self._collection_checks.pop(run_id, None)
        resource = self.resources.pop(run_id, None)
        if resource is not None:
            resource.close()

    def close(self):
        for run_id in list(self.resources):
            self.invalidate(run_id)

    def resource(self, run_id):
        root = self.store.artifacts(run_id)
        corpus = confined(root, "corpus.jsonl")
        if not corpus.is_file():
            raise HTTPException(409, "Corpus is not available")
        index = confined(root, "index")
        safe_tree(index)
        signature = tuple(
            (str(p.relative_to(index)), p.stat().st_mtime_ns, p.stat().st_size)
            for p in sorted(index.rglob("*"))
            if p.is_file()
        )
        identity = (self.identity(corpus), signature)
        resource = self.resources.get(run_id)
        if resource is None or resource.identity != identity:
            self.invalidate(run_id)
            resource = Resources(root, identity)
            self.resources[run_id] = resource
        return resource

    def search(self, run_id, body: SearchRequest):
        with self.lock:
            resource = self.resource(run_id)
            spec = body.config
            dense = (
                self.dense_resource(run_id, resource) if spec.mode != "bm25" else None
            )
            if spec.mode == "bm25":
                hits = json.loads(
                    resource.index.search(
                        body.query,
                        top_k=body.top_k,
                        config_json=spec.sparse_config.model_dump_json(),
                    )
                )
            elif spec.mode == "dense":
                hits = dense.search(body.query, top_k=body.top_k)
            else:
                sparse_hits = (
                    json.loads(
                        resource.index.search(
                            body.query,
                            top_k=spec.sparse_top_k,
                            config_json=spec.sparse_config.model_dump_json(),
                        )
                    )
                    if spec.sparse_weight
                    else []
                )
                dense_hits = (
                    dense.search(body.query, top_k=spec.dense_top_k)
                    if spec.dense_weight
                    else []
                )
                hits = rrf_fusion(
                    sparse_hits,
                    dense_hits,
                    top_k=body.top_k,
                    sparse_weight=spec.sparse_weight,
                    dense_weight=spec.dense_weight,
                    rrf_k=spec.rrf_k,
                )
            return {
                "hits": resource.enrich(hits),
                "mode": spec.mode,
                "dense_build_id": dense.report["build_id"] if dense else None,
            }
