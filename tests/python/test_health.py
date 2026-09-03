from __future__ import annotations

import json
import subprocess
import sys

from fem_core.health import build_health_report


def test_health_report_is_explicit_about_solver_boundary() -> None:
    report = build_health_report()

    assert report["status"] == "ok"
    assert report["core"] == "fem_core"
    assert report["python"]["version"]
    assert report["solvers"] == {
        "ansys": "not_checked",
        "opensees": "not_checked",
    }


def test_health_cli_emits_machine_readable_json() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "fem_core.cli", "health"],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["status"] == "ok"
    assert payload["coreVersion"] == "0.1.0"
