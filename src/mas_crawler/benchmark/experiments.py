"""Run native search experiments and evaluate their actual ranked results."""

import json
from typing import Any

from langchain.tools import tool
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict

from .._native import SearchIndex
from .evaluation import Qrels, Run, evaluate_run


class SearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_weight: float
    text_weight: float


class ExperimentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    config: SearchConfig


def evaluate_experiments(
    index: SearchIndex,
    queries: dict[str, str],
    qrels: Qrels,
    experiments: list[ExperimentSpec],
    *,
    k: int = 10,
    parallelism: int = 1,
) -> list[dict[str, Any]]:
    """Evaluate configurations on the same index, query set and human judgments."""
    if k < 1:
        raise ValueError("k must be positive")
    if not queries:
        raise ValueError("queries must not be empty")
    if queries.keys() != qrels.keys():
        raise ValueError("queries and qrels must have identical query IDs")
    if any(not judgments for judgments in qrels.values()):
        raise ValueError("Each query needs at least one relevance judgment")
    query_ids = {text: query_id for query_id, text in queries.items()}
    if len(query_ids) != len(queries):
        raise ValueError(
            "Query texts must be unique for the current Rust experiment format"
        )
    plan = {
        "experiments": [spec.model_dump() for spec in experiments],
        "queries": list(queries.values()),
        "top_k": k,
    }
    results = json.loads(index.run_experiments(json.dumps(plan), parallelism))
    reports = []
    for result in results:
        run: Run = {}
        for entry in result["results"]:
            query_id = query_ids[entry["query"]]
            run[query_id] = {hit["url"]: hit["score"] for hit in entry["hits"]}
        reports.append(
            {
                "name": result["name"],
                "config": result["config"],
                "evaluation": evaluate_run(qrels, run, k),
            }
        )
    return reports


def create_evaluation_tool(
    index: SearchIndex,
    queries: dict[str, str],
    qrels: Qrels,
    *,
    k: int = 10,
    parallelism: int = 1,
) -> BaseTool:
    """Bind a fixed benchmark and evaluation settings to an agent tool."""
    queries = queries.copy()
    qrels = {query_id: judgments.copy() for query_id, judgments in qrels.items()}

    @tool("evaluate_experiments")
    def evaluate_search_configs(
        experiments: list[ExperimentSpec],
    ) -> list[dict[str, Any]]:
        """Run named search configurations on the fixed index and labeled queries.

        Return each configuration with aggregate and per-query nDCG, precision,
        recall and judgment coverage. Higher nDCG is better; low coverage means the
        ranking contains documents without human relevance judgments.
        """
        return evaluate_experiments(
            index,
            queries,
            qrels,
            experiments,
            k=k,
            parallelism=parallelism,
        )

    return evaluate_search_configs
