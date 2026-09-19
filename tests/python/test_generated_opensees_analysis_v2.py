from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from fem_core.analysis_spec import render_opensees_analysis
from fem_core.errors import FemCoreError
from fem_core.model_spec.validator import validate_engineering_model_spec
from fem_core.solvers import get_solver_adapter

MODEL_FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")
_HEADER = (
    "time_s,load_kind,channel_id,application_type,target_type,target_id,"
    "component,quantity,value,unit\n"
)


def _model() -> dict[str, Any]:
    model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))
    model["nodalMasses"] = [{"nodeId": 3, "mUX": 100.0, "mUY": 100.0}]
    return model


def _fingerprint(model: dict[str, Any]) -> str:
    report = validate_engineering_model_spec(model)
    assert report["status"] == "VALID"
    return str(report["modelSpecFingerprint"])


def _write_load(workspace: Path, rel_path: str, *, base: bool) -> str:
    path = workspace / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if base:
        rows = (
            "0.00,TRANSIENT,EQX,UNIFORM_EXCITATION,,,X,ACCELERATION,0.0,m/s2\n"
            "0.01,TRANSIENT,EQX,UNIFORM_EXCITATION,,,X,ACCELERATION,0.2,m/s2\n"
            "0.02,TRANSIENT,EQX,UNIFORM_EXCITATION,,,X,ACCELERATION,0.0,m/s2\n"
        )
    else:
        rows = (
            "0.00,TRANSIENT,FY3,NODAL_FORCE,NODE,3,Y,FORCE,0.0,N\n"
            "0.01,TRANSIENT,FY3,NODAL_FORCE,NODE,3,Y,FORCE,100.0,N\n"
            "0.02,TRANSIENT,FY3,NODAL_FORCE,NODE,3,Y,FORCE,0.0,N\n"
        )
    content = _HEADER + rows
    path.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _static(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": _fingerprint(model),
        "analysisType": "LINEAR_STATIC",
        "units": {"force": "N"},
        "definition": {
            "loadCases": [
                {
                    "loadCaseId": "LC1",
                    "nodalLoads": [{"nodeId": 3, "FX": 0.0, "FY": -1000.0, "MZ": 0.0}],
                }
            ]
        },
        "resultRequests": [
            {
                "requestId": "U3Y",
                "loadCaseId": "LC1",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            }
        ],
    }


def _modal(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": _fingerprint(model),
        "analysisType": "MODAL",
        "units": {},
        "definition": {"modeCount": 1},
        "resultRequests": [
            {"requestId": "F1", "quantity": "NATURAL_FREQUENCY", "mode": 1},
            {
                "requestId": "S1",
                "quantity": "MODE_SHAPE",
                "mode": 1,
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            },
        ],
    }


def _transient(
    model: dict[str, Any],
    *,
    rel_path: str,
    sha256: str,
    base: bool,
) -> dict[str, Any]:
    if base:
        units: dict[str, str] = {}
        excitation: dict[str, Any] = {
            "type": "UNIFORM_BASE_EXCITATION",
            "component": "X",
            "quantity": "ACCELERATION",
            "loadArtifact": {"path": rel_path, "sha256": sha256},
        }
        request = {
            "requestId": "U3X",
            "quantity": "DISPLACEMENT",
            "target": {"type": "NODE", "id": 3},
            "component": "X",
        }
    else:
        units = {"force": "N"}
        excitation = {
            "type": "NODAL_TIME_HISTORY",
            "nodeId": 3,
            "component": "Y",
            "quantity": "FORCE",
            "loadArtifact": {"path": rel_path, "sha256": sha256},
        }
        request = {
            "requestId": "V3Y",
            "quantity": "VELOCITY",
            "target": {"type": "NODE", "id": 3},
            "component": "Y",
        }
    return {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": _fingerprint(model),
        "analysisType": "TRANSIENT",
        "units": units,
        "definition": {
            "time": {"timeStep": 0.01, "duration": 0.02},
            "damping": {"type": "NONE"},
            "excitation": excitation,
        },
        "resultRequests": [request],
    }


def _render_profiles(workspace: Path) -> dict[str, dict[str, Any]]:
    model = _model()
    nodal_sha = _write_load(workspace, "loads/force.csv", base=False)
    base_sha = _write_load(workspace, "loads/eq.csv", base=True)
    specs = {
        "static": _static(model),
        "modal": _modal(model),
        "nodal": _transient(
            model,
            rel_path="loads/force.csv",
            sha256=nodal_sha,
            base=False,
        ),
        "base": _transient(
            model,
            rel_path="loads/eq.csv",
            sha256=base_sha,
            base=True,
        ),
    }
    rendered: dict[str, dict[str, Any]] = {}
    for name, spec in specs.items():
        report = render_opensees_analysis(workspace, model, spec)
        assert report["status"] == "RENDERED"
        rendered[name] = report
    return rendered


def _options(rendered: dict[str, Any]) -> dict[str, str]:
    return {
        "responsePlanPath": rendered["artifacts"]["responsePlanPath"],
        "analysisManifestPath": rendered["artifacts"]["manifestPath"],
    }


def _adapter() -> Any:
    adapter = get_solver_adapter("opensees")
    if not adapter.status()["available"]:
        pytest.skip("OpenSeesPy optional dependency is unavailable")
    return adapter


@pytest.mark.parametrize("profile", ["static", "modal", "nodal", "base"])
def test_v2_generated_preflight_accepts_verified_profiles_and_preserves_build_domain(
    tmp_path: Path,
    profile: str,
) -> None:
    rendered = _render_profiles(tmp_path)[profile]
    adapter = _adapter()

    preflight = adapter.preflight(
        tmp_path,
        model_path=rendered["artifacts"]["analysisPath"],
        load_path=None,
        solver_options=_options(rendered),
    )

    assert preflight["status"] == "READY"
    assert preflight["generatedAnalysis"]["status"] == "VERIFIED"
    build = preflight["model"]["buildInspection"]
    assert build["nodeCount"] == 4
    assert build["elementCount"] == 3
    assert build["analysisAdvanced"] is False
    if profile == "modal":
        assert build["interceptedAnalyzeCalls"] == 0
        assert build["interceptedEigenCalls"] == 1


def test_v2_generated_solver_options_cannot_select_execution_mode(tmp_path: Path) -> None:
    rendered = _render_profiles(tmp_path)["modal"]
    adapter = _adapter()
    options = {**_options(rendered), "executionMode": "MODAL"}

    with pytest.raises(FemCoreError) as exc_info:
        adapter.preflight(
            tmp_path,
            model_path=rendered["artifacts"]["analysisPath"],
            load_path=None,
            solver_options=options,
        )
    assert exc_info.value.code == "UNSUPPORTED_SOLVER_OPTIONS"


def test_v2_generated_bundle_forbids_external_load_path(tmp_path: Path) -> None:
    rendered = _render_profiles(tmp_path)["nodal"]
    adapter = _adapter()
    external = tmp_path / "external.csv"
    external.write_text("placeholder\n", encoding="utf-8")

    with pytest.raises(FemCoreError) as exc_info:
        adapter.preflight(
            tmp_path,
            model_path=rendered["artifacts"]["analysisPath"],
            load_path="external.csv",
            solver_options=_options(rendered),
        )
    assert exc_info.value.code == "UNSUPPORTED_SOLVER_OPTIONS"


def test_v2_modal_run_uses_verified_modal_mode_and_records_canonical_artifact(tmp_path: Path) -> None:
    rendered = _render_profiles(tmp_path)["modal"]
    adapter = _adapter()

    run = adapter.run(
        tmp_path,
        model_path=rendered["artifacts"]["analysisPath"],
        load_path=None,
        solver_options=_options(rendered),
    )

    assert run["status"] == "COMPLETED"
    assert run["analysis"]["type"] == "MODAL"
    assert "modalResults" in run["outputs"]
    assert "modalResultsSha256" in run["outputs"]
    assert "structuralResponse" not in run["outputs"]
    modal_path = tmp_path / run["outputs"]["modalResults"]
    modal = json.loads(modal_path.read_text(encoding="utf-8"))
    assert modal["kind"] == "modal_result_set"
    assert {item["requestId"] for item in modal["results"]} == {"F1", "S1"}


def test_v2_transient_run_records_verified_structural_response(tmp_path: Path) -> None:
    rendered = _render_profiles(tmp_path)["nodal"]
    adapter = _adapter()

    run = adapter.run(
        tmp_path,
        model_path=rendered["artifacts"]["analysisPath"],
        load_path=None,
        solver_options=_options(rendered),
    )

    assert run["status"] == "COMPLETED"
    assert "structuralResponse" in run["outputs"]
    assert "structuralResponseSha256" in run["outputs"]
    response = json.loads((tmp_path / run["outputs"]["structuralResponse"]).read_text(encoding="utf-8"))
    channel = response["channels"][0]
    assert channel["channelId"] == "V3Y"
    assert channel["abscissaSemantic"] == "TIME"
    assert channel["abscissaUnit"] == "s"


def test_v2_tampered_bundle_fails_before_solver_run_directory_creation(tmp_path: Path) -> None:
    rendered = _render_profiles(tmp_path)["static"]
    adapter = _adapter()
    source = tmp_path / rendered["artifacts"]["analysisPath"]
    source.write_text(source.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    runs_root = tmp_path / ".femagent" / "runs"
    before = set(runs_root.iterdir()) if runs_root.is_dir() else set()

    with pytest.raises(FemCoreError) as exc_info:
        adapter.run(
            tmp_path,
            model_path=rendered["artifacts"]["analysisPath"],
            load_path=None,
            solver_options=_options(rendered),
        )
    assert exc_info.value.code == "GENERATED_ANALYSIS_ARTIFACT_MISMATCH"
    after = set(runs_root.iterdir()) if runs_root.is_dir() else set()
    assert after == before
