"""Linux worker identity survives server restarts without PID-reuse mistakes."""

from pathlib import Path


def process_start(pid: int):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return None if fields[0] == "Z" else fields[19]
    except (OSError, IndexError):
        return None


def worker_alive(metadata: dict) -> bool:
    pid = metadata.get("worker_pid")
    return (
        isinstance(pid, int)
        and metadata.get("worker_started") is not None
        and process_start(pid) == metadata["worker_started"]
    )
