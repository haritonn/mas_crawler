"""Maintainer-only checks; not needed by the exported service."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "sync_search_template.py"


def test_check_detects_drift_and_sync_restores_exact_source(tmp_path):
    script = tmp_path / "tools" / SCRIPT.name
    script.parent.mkdir()
    assert SCRIPT.is_file(), "Template snapshot maintenance command is missing"
    script.write_bytes(SCRIPT.read_bytes())
    source = tmp_path / "core/src/search.rs"
    target = tmp_path / "templates/search-service/native/src/search.rs"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_text("// original\n", encoding="utf-8")
    target.write_text("// stale\n", encoding="utf-8")
    check = subprocess.run(
        [sys.executable, str(script), "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 1
    assert "out of date" in check.stderr
    subprocess.run([sys.executable, str(script)], check=True)
    assert target.read_bytes() == source.read_bytes()
    subprocess.run([sys.executable, str(script), "--check"], check=True)
