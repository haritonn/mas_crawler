"""Package a saved BM25 experiment as an independent editable service."""

import hashlib
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from .benchmark.retrieval_experiments import RetrievalExperiment

# Only source files: never include local environments, indexes or credentials.
TEMPLATE_FILES = (
    "README.md",
    "Dockerfile",
    ".dockerignore",
    ".gitignore",
    "pyproject.toml",
    "uv.lock",
    "native/Cargo.toml",
    "native/Cargo.lock",
    "native/src/*.rs",
    "src/search_service/*.py",
    "tests/*.py",
)


def template_directory() -> Path:
    package = Path(__file__).resolve().parent
    for root in (package.parent, package.parent.parent):
        template = root / "templates" / "search-service"
        if template.is_dir():
            return template
    raise FileNotFoundError("Search-service template is missing from this installation")


def export_project(
    corpus: Path,
    experiment: RetrievalExperiment,
    output: Path,
    *,
    corpus_sha256: str,
    name: str = "Search service",
    provenance: dict | None = None,
) -> Path:
    """Write a ZIP containing the complete corpus, sources and selected weights.

    The index is rebuilt on deployment. No model calls, compilation or Docker
    execution occur here. The caller supplies the saved report's corpus digest.
    """
    if experiment.mode != "bm25":
        raise ValueError("Export currently supports BM25 only")
    template = template_directory()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="gather-export-") as temporary:
        root = Path(temporary)
        project = root / "search-service"
        project.mkdir()
        for pattern in TEMPLATE_FILES:
            for source in template.glob(pattern):
                destination = project / source.relative_to(template)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
        documents = project / "data" / "documents.jsonl"
        documents.parent.mkdir()
        shutil.copyfile(corpus, documents)
        with documents.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != corpus_sha256:
            raise ValueError("Corpus changed since evaluation; run a new comparison")
        weights = experiment.sparse_config
        config = (
            "schema_version = 1\n\n[project]\n"
            f"name = {json.dumps(name, ensure_ascii=False)}\n\n"
            '[storage]\ncorpus = "data/documents.jsonl"\n'
            'index = "indexes/lexical"\n\n[search]\n'
            f"title_weight = {weights.title_weight}\n"
            f"text_weight = {weights.text_weight}\n"
        )
        (project / "search.toml").write_text(config, encoding="utf-8")
        metadata = {
            "schema_version": 1,
            "name": name,
            "corpus_sha256": digest,
            "experiment": experiment.model_dump(mode="json"),
            "provenance": provenance or {},
        }
        (project / "export.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        readme = project / "README.md"
        instructions = (
            "# Экспорт из Gather\n\n"
            "В комплекте полный корпус источника и выбранные настройки BM25. "
            "Индекс не включён: он строится при развёртывании.\n\n"
            "Запуск из этого каталога:\n\n"
            "    uv sync --locked\n"
            "    uv run --locked search-service build\n"
            "    uv run --locked search-service serve\n\n"
            "Либо соберите Docker-образ по инструкции ниже. "
            "Gather и LLM-ключи не нужны. Происхождение и настройки — в export.json. "
            "API находится на /search, документация на /docs; "
            "пользовательский интерфейс поиска не включён.\n\n"
            "Для локальной сборки нужны Python 3.12+, uv, Rust с edition 2024 "
            "и C-компилятор. Первая сборка скачивает зависимости.\n\n"
            "## Docker\n\n"
            "    docker build -t my-search .\n"
            "    docker run --rm -p 127.0.0.1:8000:8000 my-search\n\n"
            "## API\n\n"
            "POST /search принимает JSON с query и необязательным top_k. "
            "Ответ содержит hits с id, url, title, score. GET /health проверяет доступность.\n\n"
            "## Изменения\n\n"
            "Веса полей меняются в search.toml и применяются после перезапуска. "
            "Пути в TOML относительны к самому файлу. "
            "После изменения корпуса постройте новый индекс командой "
            "`uv run --locked search-service build --output indexes/v2`, "
            "укажите его в search.toml и перезапустите сервис. "
            "Исходники Python находятся в src/search_service, Rust — в native/src.\n\n"
            "При пересборке индекса порядок документов с одинаковым BM25 score "
            "может измениться. Экспорт сам по себе не подтверждает качество поиска.\n\n"
            "Сервис не содержит аутентификации и TLS. "
            "Не публикуйте его напрямую в интернет без ограничений доступа.\n"
        )
        readme.write_text(instructions, encoding="utf-8")
        archive = Path(
            shutil.make_archive(str(root / "export"), "zip", root, "search-service")
        )
        with archive.open("rb") as source, output.open("xb") as target:
            shutil.copyfileobj(source, target)
    return output
