"""Exercise benchmark evaluation through the public CLI and a real native index."""

import json
import os
import subprocess
import sys

import pytest

from mas_crawler._native import build_index


@pytest.fixture
def evaluation_files(tmp_path):
    url = "https://fixture/iterator"
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        json.dumps({"url": url, "title": "Iterator", "text": "iterator adapters"})
        + "\n",
        encoding="utf-8",
    )
    index = tmp_path / "index"
    build_index(str(corpus), str(index))
    dataset = tmp_path / "dev.json"
    dataset.write_text(
        json.dumps(
            {
                "queries": {"q1": "iterator", "q2": "absenttoken"},
                "qrels": {"q1": {url: 3}, "q2": {url: 3}},
            }
        ),
        encoding="utf-8",
    )
    experiments = tmp_path / "experiments.json"
    experiments.write_text(
        '[{"name": "bm25-default", "mode": "bm25"}]', encoding="utf-8"
    )
    return index, dataset, experiments, tmp_path / "reports" / "evaluation.json"


def run_evaluate(files):
    index, dataset, experiments, output = files
    env = {**os.environ, "LANGSMITH_TRACING": "false"}
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mas_crawler.cli",
            "--config",
            str(dataset.parent / "missing-config.toml"),
            "benchmark",
            "evaluate",
            "--index",
            str(index),
            "--dataset",
            str(dataset),
            "--experiments",
            str(experiments),
            "--output",
            str(output),
            "--top-k",
            "1",
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


def test_cli_evaluates_bm25_without_llm_config_or_dense_build(evaluation_files):
    result = run_evaluate(evaluation_files)
    assert result.returncode == 0, result.stderr
    report = json.loads(evaluation_files[3].read_text(encoding="utf-8"))
    experiment = report["experiments"][0]
    assert experiment["name"] == "bm25-default"
    assert experiment["results"]["q2"] == []
    assert experiment["evaluation"]["aggregate"]["nDCG@1"] == pytest.approx(0.5)
    assert report["dataset"] == str(evaluation_files[1].resolve())
    assert report["top_k"] == 1
    assert "bm25-default" in result.stdout
    assert "nDCG@1" in result.stdout
    assert "cache" in result.stdout


def test_cli_requires_dense_build_for_dense_experiments(evaluation_files):
    evaluation_files[2].write_text(
        '[{"name": "dense", "mode": "dense"}]', encoding="utf-8"
    )
    result = run_evaluate(evaluation_files)
    assert result.returncode == 1
    assert "--dense-build" in result.stderr
    assert not evaluation_files[3].exists()


def test_cli_does_not_overwrite_a_report(evaluation_files):
    output = evaluation_files[3]
    output.parent.mkdir()
    output.write_text("existing report", encoding="utf-8")
    result = run_evaluate(evaluation_files)
    assert result.returncode == 1
    assert "exists" in result.stderr
    assert output.read_text(encoding="utf-8") == "existing report"


def test_cli_reports_invalid_experiment_configuration(evaluation_files):
    evaluation_files[2].write_text(
        '[{"name": "bad", "mode": "typo"}]', encoding="utf-8"
    )
    result = run_evaluate(evaluation_files)
    assert result.returncode == 1
    assert "mode" in result.stderr
    assert not evaluation_files[3].exists()
