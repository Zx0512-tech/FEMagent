from __future__ import annotations

import json
from pathlib import Path

import pytest

from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model
from fem_core.semantic_roles import inspect_semantic_roles, resolve_semantic_role


def _write_manifest(
    workspace: Path,
    *,
    fingerprint: str,
    node_id: int = 1,
    role_id: str = "TOWER_BASE_LEFT",
    role_type: str = "TOWER_BASE",
) -> Path:
    path = workspace / "semantic-roles.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "kind": "engineering_semantic_roles",
                "model": {"bundleFingerprint": fingerprint},
                "roles": [
                    {
                        "roleId": role_id,
                        "roleType": role_type,
                        "entity": {"type": "NODE", "id": node_id},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_ansys_model(workspace: Path) -> Path:
    path = workspace / "model.inp"
    path.write_text(
        "/PREP7\n"
        "ET,1,LINK180\n"
        "N,1,0,0,0\n"
        "N,2,1,0,0\n"
        "E,1,2\n",
        encoding="utf-8",
    )
    return path


def test_ansys_explicit_role_resolves_to_statically_confirmed_node(tmp_path: Path) -> None:
    _write_ansys_model(tmp_path)
    model_report = inspect_model(tmp_path, "model.inp")
    fingerprint = model_report["bundle"]["bundleFingerprint"]
    _write_manifest(tmp_path, fingerprint=fingerprint, node_id=1)

    result = resolve_semantic_role(
        tmp_path,
        model_path="model.inp",
        manifest_path="semantic-roles.json",
        role_id="TOWER_BASE_LEFT",
    )

    assert result["status"] == "RESOLVED"
    assert result["roleType"] == "TOWER_BASE"
    assert result["entity"] == {"type": "NODE", "id": 1}
    assert result["entityValidation"] == "STATICALLY_CONFIRMED"
    assert result["modelBundleFingerprint"] == fingerprint
    assert len(result["manifestSha256"]) == 64


def test_semantic_inspection_returns_all_declared_roles(tmp_path: Path) -> None:
    _write_ansys_model(tmp_path)
    fingerprint = inspect_model(tmp_path, "model.inp")["bundle"]["bundleFingerprint"]
    _write_manifest(tmp_path, fingerprint=fingerprint, node_id=2)

    result = inspect_semantic_roles(
        tmp_path,
        model_path="model.inp",
        manifest_path="semantic-roles.json",
    )

    assert result["kind"] == "semantic_role_inspection"
    assert result["status"] == "RESOLVED"
    assert result["roles"][0]["roleId"] == "TOWER_BASE_LEFT"
    assert result["roles"][0]["entityValidation"] == "STATICALLY_CONFIRMED"


def test_stale_manifest_fails_closed(tmp_path: Path) -> None:
    _write_ansys_model(tmp_path)
    _write_manifest(tmp_path, fingerprint="0" * 64)

    with pytest.raises(FemCoreError) as exc_info:
        resolve_semantic_role(
            tmp_path,
            model_path="model.inp",
            manifest_path="semantic-roles.json",
            role_id="TOWER_BASE_LEFT",
        )

    assert exc_info.value.code == "SEMANTIC_ROLE_MODEL_MISMATCH"


def test_missing_explicit_node_fails_when_topology_is_complete(tmp_path: Path) -> None:
    _write_ansys_model(tmp_path)
    fingerprint = inspect_model(tmp_path, "model.inp")["bundle"]["bundleFingerprint"]
    _write_manifest(tmp_path, fingerprint=fingerprint, node_id=999)

    with pytest.raises(FemCoreError) as exc_info:
        resolve_semantic_role(
            tmp_path,
            model_path="model.inp",
            manifest_path="semantic-roles.json",
            role_id="TOWER_BASE_LEFT",
        )

    assert exc_info.value.code == "SEMANTIC_ROLE_ENTITY_NOT_FOUND"


def test_dynamic_opensees_role_is_resolved_but_not_statically_enumerable(tmp_path: Path) -> None:
    model = tmp_path / "model.py"
    model.write_text(
        "import openseespy.opensees as ops\n"
        "ops.model('basic', '-ndm', 2, '-ndf', 2)\n"
        "for tag in range(1, 3):\n"
        "    ops.node(tag, float(tag - 1), 0.0)\n"
        "ops.element('truss', 1, 1, 2, 1.0, 1)\n",
        encoding="utf-8",
    )
    fingerprint = inspect_model(tmp_path, "model.py")["bundle"]["bundleFingerprint"]
    _write_manifest(tmp_path, fingerprint=fingerprint, node_id=2)

    result = resolve_semantic_role(
        tmp_path,
        model_path="model.py",
        manifest_path="semantic-roles.json",
        role_id="TOWER_BASE_LEFT",
    )
    inspection = inspect_semantic_roles(
        tmp_path,
        model_path="model.py",
        manifest_path="semantic-roles.json",
    )

    assert result["status"] == "RESOLVED"
    assert result["entity"] == {"type": "NODE", "id": 2}
    assert result["entityValidation"] == "NOT_STATICALLY_ENUMERABLE"
    assert inspection["status"] == "RESOLVED"
    assert inspection["roles"][0]["status"] == "RESOLVED"
    assert inspection["roles"][0]["entityValidation"] == "NOT_STATICALLY_ENUMERABLE"


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda payload: payload.update({"schemaVersion": "2.0"}), "INVALID_SEMANTIC_ROLE_MANIFEST"),
        (lambda payload: payload["roles"][0].update({"roleId": "tower-base"}), "INVALID_SEMANTIC_ROLE_MANIFEST"),
        (lambda payload: payload["roles"][0].update({"roleType": "PIER_TOP"}), "INVALID_SEMANTIC_ROLE_MANIFEST"),
        (lambda payload: payload["roles"][0].update({"entity": {"type": "ELEMENT", "id": 1}}), "INVALID_SEMANTIC_ROLE_MANIFEST"),
        (lambda payload: payload["roles"][0].update({"entity": {"type": "NODE", "id": 0}}), "INVALID_SEMANTIC_ROLE_MANIFEST"),
    ],
)
def test_invalid_manifest_shapes_fail_closed(tmp_path: Path, mutate, expected_code: str) -> None:
    _write_ansys_model(tmp_path)
    fingerprint = inspect_model(tmp_path, "model.inp")["bundle"]["bundleFingerprint"]
    manifest = _write_manifest(tmp_path, fingerprint=fingerprint)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    mutate(payload)
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FemCoreError) as exc_info:
        inspect_semantic_roles(
            tmp_path,
            model_path="model.inp",
            manifest_path="semantic-roles.json",
        )

    assert exc_info.value.code == expected_code


def test_duplicate_role_ids_fail_closed(tmp_path: Path) -> None:
    _write_ansys_model(tmp_path)
    fingerprint = inspect_model(tmp_path, "model.inp")["bundle"]["bundleFingerprint"]
    manifest = _write_manifest(tmp_path, fingerprint=fingerprint)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["roles"].append(dict(payload["roles"][0]))
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FemCoreError) as exc_info:
        inspect_semantic_roles(
            tmp_path,
            model_path="model.inp",
            manifest_path="semantic-roles.json",
        )

    assert exc_info.value.code == "INVALID_SEMANTIC_ROLE_MANIFEST"


def test_unknown_role_id_fails_closed(tmp_path: Path) -> None:
    _write_ansys_model(tmp_path)
    fingerprint = inspect_model(tmp_path, "model.inp")["bundle"]["bundleFingerprint"]
    _write_manifest(tmp_path, fingerprint=fingerprint)

    with pytest.raises(FemCoreError) as exc_info:
        resolve_semantic_role(
            tmp_path,
            model_path="model.inp",
            manifest_path="semantic-roles.json",
            role_id="GIRDER_END_A",
        )

    assert exc_info.value.code == "SEMANTIC_ROLE_NOT_FOUND"
