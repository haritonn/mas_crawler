"""Private subprocess entry point, using Python APIs rather than public CLI."""

import argparse
import logging
from pathlib import Path

from ..benchmark.optimizer import OptimizerSettings, optimize_benchmark
from ..benchmark.retrieval_experiments import evaluate_retrieval_experiments
from ..config import load_config
from .retrieval import (
    DenseRequest,
    EvaluationRequest,
    OptimizationRequest,
    RetrievalService,
    corpus_identity,
    safe_tree,
)
from .store import IDENTIFIER, Store, atomic_json, confined, read_json

logger = logging.getLogger(__name__)


def qdrant_client(url):
    from qdrant_client import QdrantClient

    return QdrantClient(url=url, timeout=120)


def build_dense(corpus, directory, profile, **kwargs):
    from ..dense import EmbeddingProfile
    from ..dense import build_dense as build

    return build(
        corpus,
        directory,
        EmbeddingProfile.model_validate(profile.model_dump()),
        **kwargs,
    )


def upload_dense(directory, client, **kwargs):
    from ..dense import upload_dense as upload

    return upload(directory, client, **kwargs)


def execute_job(service: RetrievalService, run_id: str, job_id: str):
    if not IDENTIFIER.fullmatch(job_id):
        raise ValueError("Invalid job ID")
    directory = confined(service.directory(run_id), "jobs", job_id)
    path = confined(directory, "job.json")
    # Parent publishes PID/start identity before releasing this lock.
    with service.operation_lock(run_id):
        job = read_json(path)
        if job.get("status") != "running":
            return
    corpus = confined(service.store.artifacts(run_id), "corpus.jsonl")

    def progress(stage, completed, total):
        job.update(stage=stage, completed=completed, total=total)
        atomic_json(path, job)

    def check_corpus():
        if corpus_identity(corpus) != job["corpus_sha256"]:
            raise ValueError("Corpus changed during retrieval job")

    try:
        check_corpus()
        payload = read_json(confined(directory, "request.json"))
        if job["kind"] == "dense":
            request = DenseRequest.model_validate(payload)
            build_dir = confined(directory, "build")
            report = build_dense(
                corpus,
                build_dir,
                request.profile,
                **request.model_dump(exclude={"profile"}),
                progress=progress,
            )
            safe_tree(build_dir)
            if report["source_sha256"] != job["corpus_sha256"]:
                raise ValueError("Dense build does not match the run corpus")
            check_corpus()
            client = qdrant_client(service.qdrant_url)
            try:
                upload_dense(
                    build_dir, client, batch_size=request.batch_size, progress=progress
                )
            finally:
                client.close()
            check_corpus()
            # This is the only activation point. Existing ready builds are never overwritten.
            atomic_json(
                confined(service.directory(run_id), "ready.json"),
                {
                    "job_id": job_id,
                    "build_id": report["build_id"],
                    "source_sha256": job["corpus_sha256"],
                    "qdrant_url": service.qdrant_url,
                },
            )
        elif job["kind"] == "optimization":
            expected = {key: payload.pop(key) for key in ("dev_sha256", "split_sha256")}
            request = OptimizationRequest.model_validate(payload)
            with service.operation_lock(run_id):
                package, corpus, index, identities = service.optimization_inputs(
                    run_id, job["package"]
                )
                if identities != expected:
                    raise ValueError("Accepted benchmark changed before optimization")

            def optimization_progress(stage, report):
                job.update(
                    stage=stage,
                    completed=len(report["experiments"]),
                    total=request.max_experiments,
                    model_calls=report["model_calls"],
                    max_model_calls=request.max_model_calls,
                    best_name=report["best_name"],
                )
                atomic_json(path, job)

            report = optimize_benchmark(
                package,
                confined(directory, "optimization"),
                settings=OptimizerSettings.model_validate(
                    request.model_dump(exclude={"auto_apply"})
                ),
                config=load_config(service.config_path)
                if service.config_path is not None and service.config_path.is_file()
                else None,
                corpus_path=corpus,
                index_path=index,
                progress=optimization_progress,
            )
            with service.operation_lock(run_id):
                check_corpus()
                _, _, _, identities = service.optimization_inputs(
                    run_id, job["package"]
                )
                if identities != expected:
                    raise ValueError("Accepted benchmark changed before activation")
                active = (
                    service.apply_winner(run_id, job, report)
                    if request.auto_apply
                    else None
                )
                job.update(
                    status="ready",
                    stage="ready",
                    error=None,
                    auto_applied=active is not None,
                )
                atomic_json(path, job)
        elif job["kind"] == "evaluation":
            request = EvaluationRequest.model_validate(payload)
            package = service.store.package(run_id, job["package"])
            if not service.store.accepted(package):
                raise ValueError("Accepted annotation required")
            benchmark = read_json(confined(package, "benchmark", "dev.json"))
            resource = service.resource(run_id)
            dense = (
                service.dense_resource(run_id, resource)
                if any(s.mode != "bm25" for s in request.experiments)
                else None
            )
            progress(
                "evaluation", 0, len(benchmark["queries"]) * len(request.experiments)
            )
            reports = evaluate_retrieval_experiments(
                resource.index,
                benchmark["queries"],
                benchmark["qrels"],
                request.experiments,
                dense=dense,
                k=request.top_k,
                progress=lambda completed, total: progress(
                    "evaluation", completed, total
                ),
            )
            for report in reports:
                report["results"] = {
                    query: resource.enrich(hits)
                    for query, hits in report["results"].items()
                }
            check_corpus()
            report = {
                "id": job_id,
                "created_at": job["created_at"],
                "package": job["package"],
                "split": "dev",
                "label_source": service.store.label_source(package),
                "top_k": request.top_k,
                "corpus_documents": len(resource.documents),
                "dense_build_id": dense.report["build_id"] if dense else None,
                "corpus_sha256": job["corpus_sha256"],
                "queries": benchmark["queries"],
                "qrels": benchmark["qrels"],
                "reports": reports,
            }
            atomic_json(confined(directory, "report.json"), report)
        else:
            raise ValueError("Unknown retrieval job kind")
        job.update(status="ready", stage="ready", error=None)
    except Exception as error:
        if job["kind"] == "optimization":
            # Provider errors may include request data or credentials.
            logger.error("Optimization failed (%s)", type(error).__name__)
        else:
            logger.exception("Retrieval job failed")
        job.update(
            status="failed",
            error="Retrieval job failed. See local retrieval worker.log.",
        )
    finally:
        atomic_json(path, job)
        service.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--qdrant-url", required=True)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    execute_job(
        RetrievalService(
            Store(args.runs_dir), args.qdrant_url, config_path=args.config
        ),
        args.run_id,
        args.job_id,
    )


if __name__ == "__main__":
    main()
