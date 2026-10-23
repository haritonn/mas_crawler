"""Small LangSmith helpers; tracing remains opt-in through the environment."""

from dotenv import load_dotenv
from langsmith import get_current_run_tree
from langsmith.utils import tracing_is_enabled

load_dotenv()


def record_metadata(**values: object) -> None:
    """Attach diagnostics to the active span without changing application output."""
    run = get_current_run_tree()
    if run is not None and tracing_is_enabled():
        run.add_metadata(values)
