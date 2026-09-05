from __future__ import annotations

import json
from pathlib import Path

from fem_core.result_intelligence import inspect_result


def _write_run(tmp_path: Path, *, bundle_fingerprint: str | None) -> str:
    run_id = "run_modelidentity01"
    run_dir = tmp_path / ".femagent" / "runs" / run_id
    run_dir.mkdir(parents=True)
    model = {"path": "model.py", "sha256": "b" * 64}
    if bundle_fingerprint is not None:
        model["bundleFingerprint"] = bundle_fingerprint
    manifest = {
        "schemaVersion": "1.0",
        "kind": "solver_run",
        "runId": run_id,
        "caseFingerprint": "a" * 64,
        "status": "COMPLETED",
        "solver": {"name": "UNSUPPORTED_TEST_SOLVER"},
        "model": model,
        "load": {"mode": "MODEL_SCRIPT_MANAGED"},
        "analysis": {"type": "MODEL_SCRIPT"},
        "summary": {},
        "outputs": {
            "runManifest": f".femagent/runs/{run_id}/run_manifest.json",
        },
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_id


def test_inspect_result_exposes_recorded_model_bundle_identity(tmp_path: Path) -> None:
    fingerprint = "d" * 64
    run_id = _write_run(tmp_path, bundle_fingerprint=fingerprint)

    report = inspect_result(tmp_path, run_id)

    assert report["model"] == {
        "path": "model.py",
        "bundleFingerprint": fingerprint,
    }


def test_inspect_result_does_not_invent_missing_model_bundle_identity(tmp_path: Path) -> None:
    run_id = _write_run(tmp_path, bundle_fingerprint=None)

    report = inspect_result(tmp_path, run_id)

    assert report["model"] == {
        "path": "model.py",
        "bundleFingerprint": None,
    }
