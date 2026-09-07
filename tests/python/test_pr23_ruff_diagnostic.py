from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_show_canonical_ruff_import_order(tmp_path: Path) -> None:
    source = Path("tests/python/test_opensees_model_renderer_integration.py")
    candidate = tmp_path / source.name
    candidate.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "I001", "--fix", str(candidate)],
        capture_output=True,
        text=True,
        check=False,
    )
    fixed = candidate.read_text(encoding="utf-8").splitlines()[:14]
    raise AssertionError(
        "Ruff diagnostic returnCode="
        f"{completed.returncode}\nstdout={completed.stdout}\nstderr={completed.stderr}\n"
        "fixed-head:\n"
        + "\n".join(fixed)
    )
