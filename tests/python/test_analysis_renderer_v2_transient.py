from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from fem_core.analysis_spec import render_opensees_analysis
from fem_core.analysis_spec.validator import validate_engineering_analysis_spec
from fem_core.errors import FemCoreError
from fem_core.model_spec.validator import validate_engineering_model_spec
from fem_core.solvers.opensees_generated_analysis import verify_generated_analysis_bundle

MODEL_FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")

_HEADER = (
    "time_s,load_kind,channel_id,application_type,target_type,target_id,"
    "component,quantity,value,unit\n"
)


def _model() -> dict[str, Any]:
    model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))
    model["nodalMasses"] = [{"nodeId": 3, "mUX": 100.0, "mUY": 100.0}]
    return model


def _write_artifact(workspace: Path, rel_path: str, *, base: bool) -> str:
    path = workspace / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if base:
        rows = [
            "0.00,TRANSIENT,EQX,UNIFORM_EXCITATION,,,X,ACCELERATION,0.0,m/s2\n",
            "0.01,TRANSIENT,EQX,UNIFORM_EXCITATION,,,X,ACCELERATION,0.2,m/s2\n",
            "0.02,TRANSIENT,EQX,UNIFORM_EXCITATION,,,X,ACCELERATION,-0.1,m/s2\n",
            "0.03,TRANSIENT,EQX,UNIFORM_EXCITATION,,,X,ACCELERATION,0.0,m/s2\n",
        ]
    else:
        rows = [
            "0.00,TRANSIENT,FY3,NODAL_FORCE,NODE,3,Y,FORCE,0.0,N\n",
            "0.01,TRANSIENT,FY3,NODAL_FORCE,NODE,3,Y,FORCE,100.0,N\n",
            "0.02,TRANSIENT,FY3,NODAL_FORCE,NODE,3,Y,FORCE,-50.0,N\n",
            "0.03,TRANSIENT,FY3,NODAL_FORCE,NODE,3,Y,FORCE,0.0,N\n",
        ]
    content = _HEADER + "".join(rows)
    path.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _analysis(
    model: dict[str, Any],
    *,
    rel_path: str,
    sha256: str,
    base: bool,
) -> dict[str, Any]:
    validation = validate_engineering_model_spec(model)
    assert validation["status"] == "VALID"
    if base:
        units: dict[str, str] = {}
        damping: dict[str, Any] = {"type": "RAYLEIGH", "alphaM": 0.0, "betaK": 0.002}
        excitation: dict[str, Any] = {
            "type": "UNIFORM_BASE_EXCITATION",
            "component": "X",
            "quantity": "ACCELERATION",
            "loadArtifact": {"path": rel_path, "sha256": sha256},
        }
        requests = [
            {
                "requestId": "U3X",
                "quantity": "DISPLACEMENT",
                "target": {"type": "NODE", "id": 3},
                "component": "X",
            },
            {
                "requestId": "A3X_REL",
                "quantity": "RELATIVE_ACCELERATION",
                "target": {"type": "NODE", "id": 3},
                "component": "X",
            },
        ]
    else:
        units = {"force": "N"}
        damping = {"type": "NONE"}
        excitation = {
            "type": "NODAL_TIME_HISTORY",
            "nodeId": 3,
            "component": "Y",
            "quantity": "FORCE",
            "loadArtifact": {"path": rel_path, "sha256": sha256},
        }
        requests = [
            {
                "requestId": "A3Y",
                "quantity": "ACCELERATION",
                "target": {"type": "NODE", "id": 3},
                "component": "Y",
            }
        ]
    return {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": validation["modelSpecFingerprint"],
        "analysisType": "TRANSIENT",
        "units": units,
        "definition": {
            "time": {"timeStep": 0.01, "duration": 0.03},
            "damping": damping,
            "excitation": excitation,
        },
        "resultRequests": requests,
    }


def _verify(workspace: Path, rendered: dict[str, Any]) -> dict[str, Any]:
    return verify_generated_analysis_bundle(
        workspace,
        model_path=rendered["artifacts"]["analysisPath"],
        response_plan_path=rendered["artifacts"]["responsePlanPath"],
        manifest_path=rendered["artifacts"]["manifestPath"],
    )


def test_nodal_transient_source_uses_path_plain_unit_load_and_no_rayleigh(tmp_path: Path) -> None:
    model = _model()
    sha = _write_artifact(tmp_path, "loads/force.csv", base=False)
    analysis = _analysis(model, rel_path="loads/force.csv", sha256=sha, base=False)

    rendered = render_opensees_analysis(tmp_path, model, analysis)

    assert rendered["status"] == "RENDERED"
    assert rendered["input"]["readinessProfile"] == "OPENSEES_FRAME_2D_TRANSIENT_NODAL_FORCE_V2"
    source = (tmp_path / rendered["artifacts"]["analysisPath"]).read_text(encoding="utf-8")
    assert source.count('ops.timeSeries("Path"') == 1
    assert source.count('ops.pattern("Plain"') == 1
    assert "ops.load(3, 0.0, 1.0, 0.0)" in source
    assert "ops.rayleigh(" not in source
    assert "for _femagent_step in range(3):" in source
    assert source.count("ops.analyze(1, 0.01)") == 1
    assert rendered["externalArtifacts"] == [
        {"path": "loads/force.csv", "sha256": sha, "format": "FEMAGENT_LOAD_CSV_V1"}
    ]
    assert rendered["unitConversions"] == [
        {"quantity": "TIME", "sourceUnit": "s", "targetUnit": "s", "factor": 1.0},
        {"quantity": "FORCE", "sourceUnit": "N", "targetUnit": "N", "factor": 1.0},
    ]

    verified = _verify(tmp_path, rendered)
    assert verified["executionMode"] == "SCRIPT"
    assert verified["responseContext"]["analysisType"] == "TRANSIENT"
    assert verified["responseContext"]["abscissaSemantic"] == "TIME"
    assert verified["responseContext"]["abscissaUnit"] == "s"


def test_uniform_base_source_uses_path_uniform_excitation_and_exact_rayleigh(tmp_path: Path) -> None:
    model = _model()
    sha = _write_artifact(tmp_path, "loads/eq.csv", base=True)
    analysis = _analysis(model, rel_path="loads/eq.csv", sha256=sha, base=True)

    rendered = render_opensees_analysis(tmp_path, model, analysis)

    assert rendered["status"] == "RENDERED"
    assert rendered["input"]["readinessProfile"] == "OPENSEES_FRAME_2D_TRANSIENT_UNIFORM_BASE_V2"
    source = (tmp_path / rendered["artifacts"]["analysisPath"]).read_text(encoding="utf-8")
    assert source.count('ops.timeSeries("Path"') == 1
    assert source.count('ops.pattern("UniformExcitation"') == 1
    assert 'ops.pattern("Plain"' not in source
    assert source.count("ops.rayleigh(0.0, 0.002, 0.0, 0.0)") == 1
    assert "for _femagent_step in range(3):" in source
    assert source.count("ops.analyze(1, 0.01)") == 1

    verified = _verify(tmp_path, rendered)
    channels = verified["responseContext"]["channels"]
    assert verified["executionMode"] == "SCRIPT"
    assert all(channel.get("referenceFrame") == "RELATIVE" for channel in channels)


def test_transient_relocation_keeps_spec_identity_but_changes_render_provenance(tmp_path: Path) -> None:
    model = _model()
    sha_a = _write_artifact(tmp_path, "loads/a/force.csv", base=False)
    sha_b = _write_artifact(tmp_path, "loads/b/force.csv", base=False)
    assert sha_a == sha_b
    spec_a = _analysis(model, rel_path="loads/a/force.csv", sha256=sha_a, base=False)
    spec_b = _analysis(model, rel_path="loads/b/force.csv", sha256=sha_b, base=False)

    validation_a = validate_engineering_analysis_spec(spec_a)
    validation_b = validate_engineering_analysis_spec(spec_b)
    assert validation_a["status"] == validation_b["status"] == "VALID"
    assert validation_a["analysisSpecFingerprint"] == validation_b["analysisSpecFingerprint"]

    rendered_a = render_opensees_analysis(tmp_path, model, spec_a)
    rendered_b = render_opensees_analysis(tmp_path, model, spec_b)
    assert rendered_a["analysisRenderFingerprint"] != rendered_b["analysisRenderFingerprint"]


def test_v2_verifier_rejects_external_artifact_changed_after_render(tmp_path: Path) -> None:
    model = _model()
    sha = _write_artifact(tmp_path, "loads/force.csv", base=False)
    analysis = _analysis(model, rel_path="loads/force.csv", sha256=sha, base=False)
    rendered = render_opensees_analysis(tmp_path, model, analysis)

    artifact = tmp_path / "loads/force.csv"
    artifact.write_text(artifact.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(FemCoreError) as exc_info:
        _verify(tmp_path, rendered)
    assert exc_info.value.code == "GENERATED_ANALYSIS_ARTIFACT_MISMATCH"


def test_transient_response_plan_is_structural_and_deterministic(tmp_path: Path) -> None:
    model = _model()
    sha = _write_artifact(tmp_path, "loads/force.csv", base=False)
    analysis = _analysis(model, rel_path="loads/force.csv", sha256=sha, base=False)
    rendered = render_opensees_analysis(tmp_path, model, analysis)

    plan = json.loads((tmp_path / rendered["artifacts"]["responsePlanPath"]).read_text(encoding="utf-8"))
    assert plan["schemaVersion"] == "1.0"
    assert plan["kind"] == "structural_response_plan"
    assert plan["channels"] == [
        {
            "channelId": "A3Y",
            "quantity": "ACCELERATION",
            "target": {"type": "NODE", "id": 3},
            "component": "Y",
        }
    ]

    relocated = deepcopy(analysis)
    relocated["definition"]["excitation"]["loadArtifact"]["path"] = "loads/other.csv"
    (tmp_path / "loads/other.csv").write_bytes((tmp_path / "loads/force.csv").read_bytes())
    rerendered = render_opensees_analysis(tmp_path, model, relocated)
    assert rendered["artifacts"]["responsePlanSha256"] == rerendered["artifacts"]["responsePlanSha256"]
