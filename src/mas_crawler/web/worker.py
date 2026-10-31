"""Isolated CLI supervisor; persists completion even if the web server exits."""

import argparse
import subprocess
import sys
from pathlib import Path

from .store import atomic_json, confined, read_json


def dataset_command(
    run_dir: Path, config: Path, url: str, goal: str, max_pairs: int
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "mas_crawler.cli",
        "--config",
        str(config.resolve()),
        "dataset",
        url,
        "--goal",
        goal,
        "--run-dir",
        str((run_dir / "artifacts").resolve()),
        "--max-pairs",
        str(max_pairs),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--max-pairs", type=int, required=True)
    args = parser.parse_args()
    directory = args.run_dir.resolve()
    status_path = confined(directory, "status.json")
    code = -1
    try:
        # No shell and no forked Rust execution in the web process. Logs stay
        # local; the HTTP API deliberately never serves this file.
        result = subprocess.run(
            dataset_command(
                directory, args.config, args.url, args.goal, args.max_pairs
            ),
            stdin=subprocess.DEVNULL,
            check=False,
        )
        code = result.returncode
    finally:
        metadata = read_json(status_path)
        complete = confined(directory, "artifacts", "dataset-result.json").is_file()
        metadata.update(
            status="ready" if code == 0 and complete else "failed",
            exit_code=code,
            error=None
            if code == 0 and complete
            else f"Dataset worker exited (code {code}). See local worker.log.",
        )
        atomic_json(status_path, metadata)
    raise SystemExit(code if code != 0 else (0 if complete else 1))


if __name__ == "__main__":
    main()
