from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from fem_core.model_inspection import inspect_model
from fem_core.semantic_roles.evidence import project_role_evidence


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> str:
    model = tmp_path / "model.py"
    model.write_text(
        "import openseespy.opensees as ops\n"
        "ops.model('basic', '-ndm', 2, '-ndf', 3)\n"
        "ops.node(1, 0.0, 0.0)\n"
        "ops.node(2, 1.0, 0.0)\n"
        "ops.geomTransf('Linear', 1)\n"
        "ops.element('elasticBeamColumn', 41, 1, 2, 2.0, 30000.0, 100.0, 1)\n",
        encoding="utf-8",
    )
    fingerprint = inspect_model(tmp_path, model.name)["bundle"]["bundleFingerprint"]
    (tmp_path / "semantic-roles.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "kind": "engineering_semantic_roles",
                "model": {"bundleFingerprint": fingerprint},
                "roles": [
                    {
                        "roleId": "GIRDER_MIDSPAN",
                        "roleType": "MIDSPAN",
                        "entity": {"type": "ELEMENT", "id": 41},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    run_id = "run_structevidence01"
    run_dir = tmp_path / ".femagent" / "runs" / run_id
    run_dir.mkdir(parents=True)
    response = run_dir / "structural_response.json"
    response.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "kind": "structural_response_series",
                "channels": [
                    {
                        "channelId": "girder_mz_i",
                        "quantity": "GENERALIZED_FORCE",
                        "target": {"type": "ELEMENT", "id": 41},
                        "component": "MZ",
                        "location": "END_I",
                        "unit": None,
                        "referenceFrame": "ELEMENT_LOCAL",
                        "abscissaSemantic": "SOLVER_NATIVE_RESULT_ABSCISSA",
                        "abscissaUnit": None,
                        "abscissaValues": [1.0],
                        "values": [10.0],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    summary = run_dir / "result_summary.json"
    summary.write_text(json.dumps({"nodeCount": 2, "elementCount": 1}), encoding="utf-8")
    solver_log = run_dir / "solver.log"
    solver_log.write_text("structural evidence test\n", encoding="utf-8")
    manifest = {
        "schemaVersion": "1.0",
        "kind": "solver_run",
        "runId": run_id,
        "caseFingerprint": "a" * 64,
        "status": "COMPLETED",
        "solver": {"name": "OPENSEESPY", "executionMode": "ISOLATED_WORKER_PROCESS"},
        "model": {"path": model.name, "sha256": "b" * 64, "bundleFingerprint": fingerprint},
        "load": {"mode": "MODEL_SCRIPT_MANAGED"},
        "analysis": {"type": "MODEL_SCRIPT"},
        "summary": json.loads(summary.read_text(encoding="utf-8")),
        "outputs": {
            "runManifest": f".femagent/runs/{run_id}/run_manifest.json",
            "structuralResponse": f".femagent/runs/{run_id}/structural_response.json",
            "structuralResponseSha256": _sha(response),
            "resultSummary": f".femagent/runs/{run_id}/result_summary.json",
            "resultSummarySha256": _sha(summary),
            "solverLog": f".femagent/runs/{run_id}/solver.log",
            "solverLogSha256": _sha(solver_log),
        },
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_id


def test_element_role_structural_evidence_preserves_full_identity(tmp_path: Path) -> None:
    run_id = _fixture(tmp_path)

    report = project_role_evidence(
        tmp_path,
        project_id="bridge-demo",
        model_path="model.py",
        manifest_path="semantic-roles.json",
        role_id="GIRDER_MIDSPAN",
        run_ref=run_id,
        evidence_id="EVID-STRUCT-001",
        quantity="GENERALIZED_FORCE",
        component="MZ",
        location="END_I",
        operation="SUMMARY",
    )

    assert report["limitations"] == []
    evidence = report["verifiedEvidence"][0]
    assert evidence["status"] == "VERIFIED"
    assert evidence["metric"]["target"] == {"type": "ELEMENT", "id": 41}
    assert evidence["metric"]["quantity"] == "GENERALIZED_FORCE"
    assert evidence["metric"]["component"] == "MZ"
    assert evidence["metric"]["location"] == "END_I"
    assert evidence["metric"]["referenceFrame"] == "ELEMENT_LOCAL"
    assert evidence["metric"]["unit"] is None
    assert evidence["provenance"]["semanticRole"]["entity"] == {"type": "ELEMENT", "id": 41}
