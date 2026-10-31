"""Confined filesystem access and non-destructive annotation overlays."""

import csv
import io
import json
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException

from ..benchmark.dataset import AnnotationPair, import_annotation_csv

IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


def confined(root: Path, *parts: str) -> Path:
    """Reject symlinks, even ones pointing back into the root."""
    path = root
    for part in parts:
        for segment in Path(part).parts:
            if segment in ("..", ".") or Path(segment).is_absolute():
                raise HTTPException(404, "Artifact not found")
            path = path / segment
            if path.is_symlink():
                raise HTTPException(404, "Artifact not found")
    if not path.resolve().is_relative_to(root.resolve()):
        raise HTTPException(404, "Artifact not found")
    return path


def read_json(path: Path, default=None):
    if not path.exists():
        return {} if default is None else default
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("Artifact must contain a JSON object")
    return data


def atomic_write(path: Path, text: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".ui-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path: Path, data: dict) -> None:
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))


def csv_text(pairs: list[AnnotationPair]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(AnnotationPair.model_fields))
    writer.writeheader()
    for pair in pairs:
        writer.writerow(pair.model_dump())
    return output.getvalue()


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        if not IDENTIFIER.fullmatch(run_id):
            raise HTTPException(404, "Run not found")
        path = confined(self.root, run_id)
        if not path.is_dir():
            raise HTTPException(404, "Run not found")
        return path

    def artifacts(self, run_id: str) -> Path:
        path = self.run_dir(run_id)
        # Web-created runs keep metadata outside the CLI-owned directory. The CLI
        # intentionally refuses an already existing --run-dir.
        metadata = read_json(confined(path, "status.json"))
        return confined(path, "artifacts") if metadata.get("web_managed") else path

    def package(self, run_id: str, package: str) -> Path:
        if not IDENTIFIER.fullmatch(package):
            raise HTTPException(404, "Package not found")
        root = self.artifacts(run_id)
        path = confined(root, package)
        if not path.is_dir() or not confined(path, "source.json").is_file():
            raise HTTPException(404, "Package not found")
        return path

    @staticmethod
    def accepted(package: Path) -> bool:
        return confined(package, "benchmark", "split.json").is_file()

    @staticmethod
    def label_source(package: Path):
        split = read_json(confined(package, "benchmark", "split.json"))
        provenance = read_json(confined(package, "label-provenance.json"))
        source = read_json(confined(package, "source.json"))
        return (
            split.get("label_source")
            or provenance.get("label_source")
            or source.get("label_source")
        )

    @staticmethod
    def pairs(package: Path) -> list[AnnotationPair]:
        source = read_json(confined(package, "source.json"))
        raw_pairs = source.get("pairs")
        if not isinstance(raw_pairs, list) or any(
            not isinstance(raw, dict) for raw in raw_pairs
        ):
            raise ValueError("Invalid pair tasks")
        pairs = [
            AnnotationPair.model_validate(
                {key: raw.get(key) for key in AnnotationPair.model_fields}
            )
            for raw in raw_pairs
        ]
        original = {pair.pair_id: pair for pair in pairs}
        if len(original) != len(pairs):
            raise ValueError("Duplicate pair IDs")
        csv_path = confined(package, "annotation.csv")
        if csv_path.exists():
            for row in import_annotation_csv(csv_path):
                # CSV never defines tasks: only original tasks and their labels.
                if row.pair_id not in original:
                    raise ValueError("Annotation CSV contains unknown pair")
                original[row.pair_id].relevance = row.relevance
        overlay = read_json(confined(package, "ui-labels.json"))
        for pair_id, relevance in overlay.items():
            if pair_id not in original:
                raise ValueError("Saved label references unknown pair")
            original[pair_id] = original[pair_id].model_copy(
                update={"relevance": relevance}
            )
            AnnotationPair.model_validate(original[pair_id].model_dump())
        return list(original.values())

    def delete(self, run_id: str, component: str, package: str | None = None) -> None:
        """Remove only selected, preflighted artifacts; never follow symlinks.

        shutil.rmtree uses fd-based symlink attack protection on supported hosts,
        and unlinks nested symlinks rather than traversing their destinations.
        """
        run = self.run_dir(run_id)
        if component == "all":
            if not shutil.rmtree.avoids_symlink_attacks:
                raise HTTPException(409, "Safe directory deletion is unavailable")
            shutil.rmtree(run)
            return
        root = self.artifacts(run_id)
        if component == "package":
            targets = [self.package(run_id, package or "")]
            names = ["dataset-result.json"]
        elif component == "plan":
            targets = []
            names = ["crawl-plan.json"]
        else:
            targets = []
            names = ["index", "result.json", "dataset-result.json"]
            if component == "corpus":
                names += ["corpus.jsonl", "crawl-report.json"]
                if root.is_dir():
                    for path in root.iterdir():
                        if path.is_symlink() or not path.is_dir():
                            continue
                        if confined(path, "source.json").is_file():
                            targets.append(confined(root, path.name))
        # Resolve every target before the first mutation, including absent files.
        targets += [confined(root, name) for name in names]
        if not shutil.rmtree.avoids_symlink_attacks:
            raise HTTPException(409, "Safe directory deletion is unavailable")
        for path in targets:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()

    def documents(self, run_id: str, offset: int, limit: int, q: str) -> dict:
        corpus = confined(self.artifacts(run_id), "corpus.jsonl")
        if not corpus.is_file():
            raise HTTPException(409, "Corpus is not available")
        query = q.casefold()
        documents = []
        total = 0
        with corpus.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                if query and not any(query in record[key].casefold() for key in ("title", "url")):
                    continue
                if offset <= total < offset + limit:
                    documents.append({key: record[key] for key in ("url", "title", "text")})
                total += 1
        return {"documents": documents, "total": total, "offset": offset, "limit": limit}

    def describe(self, run_id: str) -> dict:
        run = self.run_dir(run_id)
        root = self.artifacts(run_id)
        meta = read_json(confined(run, "status.json"))
        ui = read_json(confined(run, "ui.json"))
        result = read_json(confined(root, "result.json"))
        dataset = read_json(confined(root, "dataset-result.json"))
        plan = read_json(confined(root, "crawl-plan.json"))
        packages = []
        goals = []
        if root.is_dir():
            for path in sorted(root.iterdir()):
                if (
                    path.is_symlink()
                    or not path.is_dir()
                    or not IDENTIFIER.fullmatch(path.name)
                ):
                    continue
                if not confined(path, "source.json").is_file():
                    continue
                pairs = self.pairs(path)
                goals.append(read_json(confined(path, "source.json")).get("goal", ""))
                packages.append(
                    {
                        "id": path.name,
                        "pairs": len(pairs),
                        "labeled": sum(pair.relevance is not None for pair in pairs),
                        "accepted": self.accepted(path),
                        "label_source": self.label_source(path),
                    }
                )
        stage = "analyze"
        if confined(root, "crawl-plan.json").exists():
            stage = "crawl"
        if confined(root, "crawl-report.json").exists():
            stage = "index"
        if confined(root, "result.json").exists():
            stage = "annotation"
        if packages:
            stage = "ready"
        status = meta.get("status")
        if status not in ("running", "failed", "interrupted"):
            status = "ready" if packages else ("collected" if result else "interrupted")
        corpus = confined(root, "corpus.jsonl")
        documents = result.get("indexed_documents") if corpus.is_file() else 0
        if documents is None or not confined(root, "index").is_dir():
            documents = 0
            if corpus.is_file():
                with corpus.open(encoding="utf-8") as handle:
                    documents = sum(bool(line.strip()) for line in handle)
        url = (
            meta.get("url")
            or dataset.get("url")
            or next(iter(plan.get("seed_urls", [])), "")
        )
        goal = meta.get("goal") or dataset.get("goal") or next(iter(goals), "")
        return {
            "id": run_id,
            "name": ui.get("name", meta.get("name", run_id)),
            "archived": bool(ui.get("archived", False)),
            "components": {
                "plan": confined(root, "crawl-plan.json").is_file(),
                "corpus": corpus.is_file(),
                "index": bool(result) and confined(root, "index").is_dir(),
            },
            "url": url,
            "goal": goal,
            "status": status,
            "stage": stage,
            "documents": documents,
            "pairs": sum(p["pairs"] for p in packages),
            "labeled": sum(p["labeled"] for p in packages),
            "created_at": meta.get("created_at")
            or datetime.fromtimestamp(run.stat().st_ctime, UTC).isoformat(),
            "error": meta.get("error"),
            "packages": packages,
        }
