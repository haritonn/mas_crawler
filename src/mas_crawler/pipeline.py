import json
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import get_current_run_tree, traceable
from langsmith.utils import tracing_is_enabled

from ._native import build_index
from .crawl_plan import CrawlPlan
from .crawler import crawl_site
from .explorer import explore_site
from .observability import record_metadata


class PipelineState(TypedDict):
    url: str
    goal: str
    run_dir: Path
    plan: NotRequired[CrawlPlan]
    crawl_report: NotRequired[dict[str, Any]]
    indexed_documents: NotRequired[int]
    index_path: NotRequired[str]


def analyze_site(state: PipelineState) -> dict[str, Any]:
    report = explore_site(state["url"], state["goal"])
    if report.plan is None:
        raise RuntimeError(report.summary)
    with (state["run_dir"] / "crawl-plan.json").open("x", encoding="utf-8") as file:
        file.write(report.plan.model_dump_json(indent=2))
    return {"plan": report.plan}


def collect_corpus(state: PipelineState) -> dict[str, Any]:
    plan = state.get("plan")
    if plan is None:
        raise RuntimeError("Crawl requires a prepared plan")
    report = crawl_site(plan, state["run_dir"] / "corpus.jsonl")
    report_path = state["run_dir"] / "crawl-report.json"
    with report_path.open("x", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    if report["succeeded"] == 0:
        raise RuntimeError(f"No documents collected; see {report_path}")
    return {"crawl_report": report}


@traceable(name="build_index", tags=["mas-crawler", "index"])
def create_index(state: PipelineState) -> dict[str, Any]:
    index_path = state["run_dir"] / "index"
    count = build_index(str(state["run_dir"] / "corpus.jsonl"), str(index_path))
    return {"indexed_documents": count, "index_path": str(index_path)}


def entry(state: PipelineState) -> Literal["analyze", "crawl"]:
    return "crawl" if state.get("plan") is not None else "analyze"


def create_pipeline():
    builder = StateGraph(PipelineState)
    builder.add_node("analyze", analyze_site)
    builder.add_node("crawl", collect_corpus)
    builder.add_node("index", create_index)

    builder.add_conditional_edges(START, entry)
    builder.add_edge("analyze", "crawl")
    builder.add_edge("crawl", "index")
    builder.add_edge("index", END)

    return builder.compile()


@traceable(name="build_search_system", tags=["mas-crawler", "build"])
def build_search_system(
    url: str,
    goal: str,
    run_dir: Path,
    plan: CrawlPlan | None = None,
) -> dict[str, Any]:
    record_metadata(
        mode="saved_plan" if plan is not None else "explore",
        run_dir=str(run_dir),
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    run = get_current_run_tree()
    if run is not None and tracing_is_enabled():
        (run_dir / "trace-id.txt").write_text(str(run.trace_id) + "\n", encoding="utf-8")
    state: PipelineState = {"url": url, "goal": goal, "run_dir": run_dir}
    if plan is not None:
        state["plan"] = plan
        with (run_dir / "crawl-plan.json").open("x", encoding="utf-8") as file:
            file.write(plan.model_dump_json(indent=2))

    pipeline = create_pipeline()
    final_state = pipeline.invoke(state, config={"run_name": "crawl_pipeline"})
    result = {
        "index_path": final_state["index_path"],
        "indexed_documents": final_state["indexed_documents"],
        "crawl_report": final_state["crawl_report"],
    }
    with (run_dir / "result.json").open("x", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    return result
