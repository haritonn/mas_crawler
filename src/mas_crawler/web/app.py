"""Loopback-only API. Never deploy this unauthenticated server publicly."""

import argparse
import ipaddress
import json
import re
import subprocess
import sys
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .._native import SearchIndex
from ..benchmark.experiments import ExperimentSpec, SearchConfig, evaluate_experiments
from ..benchmark.workflow import accept_benchmark
from .store import (
    IDENTIFIER,
    Store,
    atomic_json,
    atomic_write,
    confined,
    csv_text,
    read_json,
)


class NewRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=2048)
    goal: str = Field(min_length=1, max_length=4000)
    max_pairs: int = Field(default=20, ge=4, le=100, strict=True)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        parts = urlsplit(value)
        if (
            parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or any(c.isspace() for c in value)
        ):
            raise ValueError("URL must be HTTP(S), without credentials")
        try:
            _ = parts.port
        except ValueError:
            raise ValueError("Invalid URL port") from None
        return value

    @field_validator("goal")
    @classmethod
    def valid_goal(cls, value):
        if not value.strip():
            raise ValueError("Goal must not be blank")
        return value.strip()


class RunUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default=None)
    archived: bool = Field(default=None, strict=True)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        value = value.strip()
        if not value or len(value) > 100:
            raise ValueError("Name must contain 1 to 100 characters")
        return value


class DeleteRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component: Literal["all", "corpus", "index", "plan", "package"]
    package: str | None = None
    confirm: str


class Grade(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relevance: int | None = Field(ge=0, le=3, strict=True)


def create_app(
    *,
    runs_dir: Path = Path("runs"),
    config: Path = Path("config.toml"),
    static_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="MAS Crawler local API", description=__doc__)
    store = Store(Path(runs_dir))
    config = Path(config).resolve()
    static_dir = (
        Path(static_dir)
        if static_dir is not None
        else Path(__file__).resolve().parents[3] / "frontend" / "dist"
    ).resolve()
    lock = threading.RLock()
    workers: dict[str, subprocess.Popen] = {}
    app.state.store = store

    def poll_workers():
        for run_id, process in list(workers.items()):
            code = process.poll()
            if code is None:
                continue
            path = confined(store.run_dir(run_id), "status.json")
            metadata = read_json(path)
            if metadata.get("status") == "running":
                metadata.update(
                    status="failed",
                    error=f"Dataset worker exited (code {code}). See local worker.log.",
                )
                atomic_json(path, metadata)
            del workers[run_id]

    # A previous web server's worker may still be finishing; never mark a live
    # worker interrupted or allow another paid crawl alongside it.
    def refresh():
        poll_workers()
        for path in store.root.iterdir():
            if (
                path.is_symlink()
                or not path.is_dir()
                or not IDENTIFIER.fullmatch(path.name)
            ):
                continue
            status_path = confined(path, "status.json")
            meta = read_json(status_path)
            if meta.get("status") != "running" or path.name in workers:
                continue
            if not worker_alive(meta):
                meta.update(
                    status="interrupted",
                    error="Dataset worker stopped before completion.",
                )
                atomic_json(status_path, meta)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Never echo user inputs (which might accidentally contain credentials).
        messages = [
            ".".join(str(p) for p in e["loc"]) + ": " + e["msg"] for e in error.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": "; ".join(messages)})

    @app.exception_handler(TypeError)
    @app.exception_handler(KeyError)
    @app.exception_handler(ValueError)
    async def invalid_artifact(request, error):
        return JSONResponse(
            status_code=422,
            content={"detail": "Invalid or incomplete run artifacts or annotations."},
        )

    @app.exception_handler(OSError)
    async def inaccessible_artifact(request, error):
        return JSONResponse(
            status_code=409, content={"detail": "Run artifact is unavailable."}
        )

    @app.exception_handler(RuntimeError)
    async def native_error(request, error):
        return JSONResponse(
            status_code=409,
            content={"detail": "The index or run is not ready for this operation."},
        )

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # No CORS: browsers on foreign origins must not initiate paid jobs or
        # mutate grades on this local unauthenticated API (including form posts).
        host = urlsplit("http://" + request.headers.get("host", "")).hostname
        if not is_loopback_host(host) and host != "testserver":
            return JSONResponse(
                status_code=400, content={"detail": "Invalid local host."}
            )
        origin = request.headers.get("origin")
        if origin and not is_loopback_host(urlsplit(origin).hostname):
            return JSONResponse(
                status_code=403,
                content={"detail": "Cross-origin requests are not allowed."},
            )
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse(
                status_code=403,
                content={"detail": "Cross-site requests are not allowed."},
            )
        return await call_next(request)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/runs")
    def runs(include_archived: bool = False):
        with lock:
            refresh()
            items = []
            for path in store.root.iterdir():
                if (
                    path.is_symlink()
                    or not path.is_dir()
                    or not IDENTIFIER.fullmatch(path.name)
                ):
                    continue
                if not any(
                    (path / name).exists()
                    for name in [
                        "status.json",
                        "ui.json",
                        "crawl-plan.json",
                        "corpus.jsonl",
                        "result.json",
                        "annotation",
                    ]
                ):
                    continue
                try:
                    item = store.describe(path.name)
                    if include_archived or not item["archived"]:
                        items.append(item)
                except (TypeError, KeyError, ValueError, OSError, HTTPException):
                    # An incomplete/tampered run must not hide other saved runs.
                    continue
            return {
                "runs": sorted(items, key=lambda item: item["created_at"], reverse=True)
            }

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        with lock:
            refresh()
            return store.describe(run_id)

    def require_idle(run_id: str):
        refresh()
        metadata = read_json(confined(store.run_dir(run_id), "status.json"))
        if run_id in workers or worker_alive(metadata) or metadata.get("status") == "running":
            raise HTTPException(409, "A dataset worker is active for this run")

    @app.patch("/api/runs/{run_id}")
    def update_run(run_id: str, body: RunUpdate):
        with lock:
            require_idle(run_id)
            path = confined(store.run_dir(run_id), "ui.json")
            metadata = read_json(path)
            metadata.update(body.model_dump(exclude_unset=True))
            atomic_json(path, metadata)
            return store.describe(run_id)

    @app.post("/api/runs/{run_id}/delete")
    def delete_run(run_id: str, body: DeleteRun):
        if body.confirm != run_id:
            raise HTTPException(422, "Confirmation must equal the exact run ID")
        if body.component == "package" and not body.package:
            raise HTTPException(422, "Package is required")
        with lock:
            require_idle(run_id)
            store.delete(run_id, body.component, body.package)
            return {"deleted": True}

    @app.post("/api/runs")
    def new_run(body: NewRun):
        with lock:
            refresh()
            for path in store.root.iterdir():
                if path.is_dir() and not path.is_symlink():
                    metadata = read_json(confined(path, "status.json"))
                    if metadata.get("status") == "running":
                        raise HTTPException(409, "A dataset job is already running")
            host = urlsplit(body.url).hostname or "run"
            slug = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")[:60] or "run"
            run_id = f"{slug}-{uuid.uuid4().hex[:12]}"
            directory = confined(store.root, run_id)
            directory.mkdir()
            metadata = {
                "web_managed": True,
                "url": body.url,
                "goal": body.goal,
                "name": host,
                "created_at": datetime.now(UTC).isoformat(),
                "status": "running",
                "error": None,
            }
            atomic_json(directory / "status.json", metadata)
            try:
                with (directory / "worker.log").open("xb") as logfile:
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "mas_crawler.web.worker",
                            "--run-dir",
                            str(directory),
                            "--config",
                            str(config),
                            "--url",
                            body.url,
                            "--goal",
                            body.goal,
                            "--max-pairs",
                            str(body.max_pairs),
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=logfile,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                workers[run_id] = process
                metadata.update(
                    worker_pid=process.pid, worker_started=process_start(process.pid)
                )
                # Worker may have finished very quickly: don't overwrite its result.
                current = read_json(directory / "status.json")
                current.update(
                    worker_pid=process.pid, worker_started=metadata["worker_started"]
                )
                atomic_json(directory / "status.json", current)
            except OSError:
                metadata.update(
                    status="failed", error="Unable to launch dataset worker."
                )
                atomic_json(directory / "status.json", metadata)
                raise HTTPException(503, "Unable to launch dataset worker") from None
            return store.describe(run_id)

    @app.get("/api/runs/{run_id}/pairs")
    def pairs(run_id: str, package: str = "annotation"):
        with lock:
            directory = store.package(run_id, package)
            return {
                "pairs": [pair.model_dump() for pair in store.pairs(directory)],
                "accepted": store.accepted(directory),
                "label_source": store.label_source(directory),
            }

    @app.patch("/api/runs/{run_id}/pairs/{pair_id}")
    def grade(run_id: str, pair_id: str, body: Grade, package: str = "annotation"):
        with lock:
            directory = store.package(run_id, package)
            if store.accepted(directory) or confined(directory, "benchmark").exists():
                raise HTTPException(409, "Accepted packages are immutable")
            items = store.pairs(directory)
            if pair_id not in {pair.pair_id for pair in items}:
                raise HTTPException(404, "Pair not found")
            path = confined(directory, "ui-labels.json")
            labels = read_json(path)
            labels[pair_id] = body.relevance
            atomic_json(path, labels)
            return {
                "saved": True,
                "labeled": sum(
                    pair.relevance is not None for pair in store.pairs(directory)
                ),
                "total": len(items),
            }

    @app.get("/api/runs/{run_id}/export")
    def export(run_id: str, package: str = "annotation"):
        with lock:
            directory = store.package(run_id, package)
            return Response(
                csv_text(store.pairs(directory)),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="{run_id}-{package}.csv"'
                },
            )

    @app.post("/api/runs/{run_id}/accept")
    def accept(run_id: str, package: str = "annotation"):
        with lock:
            directory = store.package(run_id, package)
            if confined(directory, "benchmark").exists():
                raise HTTPException(
                    409, "Package already accepted or acceptance incomplete"
                )
            items = store.pairs(directory)
            from ..benchmark.dataset import validate_annotations

            validate_annotations(items)
            source = store.label_source(directory)
            # Preflight every known output to reject symlink-based writes.
            path = confined(directory, "ui-annotations.csv")
            atomic_write(path, csv_text(items))
            result = accept_benchmark(directory, path)
            if source and source != "human":
                split_path = confined(directory, "benchmark", "split.json")
                split = read_json(split_path)
                split["label_source"] = source
                atomic_json(split_path, split)
            return result

    @app.get("/api/runs/{run_id}/documents")
    def documents(
        run_id: str,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=20, ge=1, le=50),
        q: str = Query(default="", max_length=2000),
    ):
        with lock:
            return store.documents(run_id, offset, limit, q)

    @app.get("/api/runs/{run_id}/search")
    def search(
        run_id: str,
        q: str = Query(min_length=1, max_length=2000),
        top_k: int = Query(default=10, ge=1, le=20),
    ):
        root = store.artifacts(run_id)
        index_path = confined(root, "index")
        if not index_path.is_dir():
            raise HTTPException(409, "Search index is not ready")
        index = SearchIndex(str(index_path))
        hits = json.loads(index.search(q, top_k))
        corpus = confined(root, "corpus.jsonl")
        texts = {}
        wanted = {hit["url"] for hit in hits}
        if corpus.is_file():
            with corpus.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        document = json.loads(line)
                        if document["url"] in wanted:
                            texts[document["url"]] = document["text"][:1200]
        return {
            "hits": [
                {
                    "url": hit["url"],
                    "title": hit["title"],
                    "score": hit["score"],
                    "text": texts.get(hit["url"], ""),
                }
                for hit in hits
            ]
        }

    @app.post("/api/runs/{run_id}/evaluate")
    def evaluate(run_id: str, package: str = "annotation"):
        with lock:
            root = store.artifacts(run_id)
            if not confined(root, "index").is_dir() or not read_json(confined(root, "result.json")):
                raise HTTPException(409, "Completed search index is required")
            directory = store.package(run_id, package)
            if not store.accepted(directory):
                raise HTTPException(409, "Accept labels before evaluating")
            benchmark = read_json(confined(directory, "benchmark", "dev.json"))
            root = store.artifacts(run_id)
            index = SearchIndex(str(confined(root, "index")))
            specs = [
                ExperimentSpec(
                    name="equal", config=SearchConfig(title_weight=1, text_weight=1)
                ),
                ExperimentSpec(
                    name="title-boost",
                    config=SearchConfig(title_weight=3, text_weight=1),
                ),
            ]
            return {
                "reports": evaluate_experiments(
                    index, benchmark["queries"], benchmark["qrels"], specs, k=5
                ),
                "split": "dev",
                "label_source": store.label_source(directory),
            }

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "API endpoint not found")
        target = (
            confined(static_dir, path) if path else confined(static_dir, "index.html")
        )
        if target.is_file():
            return FileResponse(target)
        index = confined(static_dir, "index.html")
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(404, "Frontend build not found")

    return app


def process_start(pid: int):
    """Linux process start ticks prevent PID-reuse mistakes after server restart."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def worker_alive(metadata: dict) -> bool:
    pid = metadata.get("worker_pid")
    return (
        isinstance(pid, int)
        and metadata.get("worker_started") is not None
        and process_start(pid) == metadata["worker_started"]
    )


def is_loopback_host(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    args = parser.parse_args()
    try:
        local = args.host == "localhost" or ipaddress.ip_address(args.host).is_loopback
    except ValueError:
        local = False
    if not local:
        parser.error("This unauthenticated application only supports loopback hosts")
    import uvicorn

    uvicorn.run(
        create_app(runs_dir=args.runs_dir, config=args.config),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
