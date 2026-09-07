from __future__ import annotations

import json
import shutil
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from fem_core.errors import FemCoreError
from fem_core.model_spec.readiness import evaluate_engineering_model_readiness
from fem_core.model_spec.validator import validate_engineering_model_spec
from fem_core.pathing import workspace_relative_path

RENDER_SCHEMA = "FEMAGENT_OPENSEES_RENDER_V1"
RENDERER_NAME = "OPENSEES_FRAME_2D_V1"
RENDERER_VERSION = "1.0"
SUPPORTED_READINESS_PROFILE = "FRAME_2D_ELASTIC_READINESS_V1"
_GEOM_TRANSF_TAG = 1


def _new_render_id() -> str:
    return f"render_{uuid4().hex[:16]}"


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _format_float(value: Any) -> str:
    number = float(value)
    if number == 0.0:
        return "0.0"
    return repr(number)


def _blocked_result(readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": RENDER_SCHEMA,
        "status": "BLOCKED",
        "reason": "MODEL_NOT_READY",
        "readiness": readiness,
        "renderId": None,
        "artifacts": None,
        "renderFingerprint": None,
    }


def _lookup_by_id(
    items: list[dict[str, Any]],
    identifier: int,
    *,
    namespace: str,
) -> dict[str, Any]:
    for item in items:
        if item["id"] == identifier:
            return item
    raise FemCoreError(
        "OPENSEES_RENDER_INTERNAL_INVARIANT",
        f"Validated ModelSpec lost referenced {namespace} {identifier}",
        details={"namespace": namespace, "id": identifier},
    )


def _constraint_flags(dofs: list[str]) -> tuple[int, int, int]:
    selected = set(dofs)
    return (
        1 if "UX" in selected else 0,
        1 if "UY" in selected else 0,
        1 if "RZ" in selected else 0,
    )


def _render_source(spec: dict[str, Any]) -> str:
    lines = [
        "import openseespy.opensees as ops",
        "",
        "ops.wipe()",
        'ops.model("basic", "-ndm", 2, "-ndf", 3)',
        "",
    ]

    for node in sorted(spec["nodes"], key=lambda item: item["id"]):
        lines.append(
            f"ops.node({node['id']}, {_format_float(node['x'])}, {_format_float(node['y'])})"
        )

    if spec["constraints"]:
        lines.append("")
        for constraint in sorted(spec["constraints"], key=lambda item: item["nodeId"]):
            ux, uy, rz = _constraint_flags(constraint["dofs"])
            lines.append(f"ops.fix({constraint['nodeId']}, {ux}, {uy}, {rz})")

    if spec["nodalMasses"]:
        lines.append("")
        for mass in sorted(spec["nodalMasses"], key=lambda item: item["nodeId"]):
            lines.append(
                "ops.mass("
                f"{mass['nodeId']}, {_format_float(mass['mUX'])}, "
                f"{_format_float(mass['mUY'])}, 0.0)"
            )

    lines.extend(["", f'ops.geomTransf("Linear", {_GEOM_TRANSF_TAG})', ""])

    materials = list(spec["materials"])
    sections = list(spec["sections"])
    for element in sorted(spec["elements"], key=lambda item: item["id"]):
        material = _lookup_by_id(
            materials,
            element["materialId"],
            namespace="material",
        )
        section = _lookup_by_id(
            sections,
            element["sectionId"],
            namespace="section",
        )
        lines.append(
            'ops.element("elasticBeamColumn", '
            f"{element['id']}, {element['nodeI']}, {element['nodeJ']}, "
            f"{_format_float(section['area'])}, "
            f"{_format_float(material['youngsModulus'])}, "
            f"{_format_float(section['iz'])}, {_GEOM_TRANSF_TAG})"
        )

    return "\n".join(lines) + "\n"


def _render_fingerprint(model_spec_fingerprint: str, model_sha256: str) -> str:
    payload = json.dumps(
        {
            "rendererName": RENDERER_NAME,
            "rendererVersion": RENDERER_VERSION,
            "modelSpecFingerprint": model_spec_fingerprint,
            "modelSha256": model_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _artifact_root(workspace: Path) -> Path:
    root = workspace.resolve()
    generated = (root / ".femagent" / "generated-models").resolve()
    try:
        generated.relative_to(root)
    except ValueError as exc:
        raise FemCoreError(
            "OPENSEES_RENDER_WRITE_FAILED",
            "Generated-model artifact directory resolves outside the active workspace",
        ) from exc
    return generated


def render_opensees_frame_2d(workspace: Path, spec: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise FemCoreError(
            "OPENSEES_RENDER_SPEC_NOT_OBJECT",
            "OpenSees renderer requires a ModelSpec JSON object",
        )

    readiness = evaluate_engineering_model_readiness(spec)
    if readiness["status"] != "READY":
        return _blocked_result(readiness)
    if readiness.get("profile") != SUPPORTED_READINESS_PROFILE:
        raise FemCoreError(
            "OPENSEES_RENDER_UNSUPPORTED_PROFILE",
            "OpenSees Frame 2D renderer received an unsupported readiness profile",
            details={
                "expected": SUPPORTED_READINESS_PROFILE,
                "received": readiness.get("profile"),
            },
        )

    validation = validate_engineering_model_spec(spec)
    normalized = validation.get("normalizedSpec")
    model_spec_fingerprint = validation.get("modelSpecFingerprint")
    if (
        validation.get("status") != "VALID"
        or not isinstance(normalized, dict)
        or not isinstance(model_spec_fingerprint, str)
        or model_spec_fingerprint != readiness.get("modelSpecFingerprint")
    ):
        raise FemCoreError(
            "OPENSEES_RENDER_INTERNAL_INVARIANT",
            "Readiness and ModelSpec validation disagree at the renderer boundary",
        )

    source = _render_source(normalized)
    source_bytes = source.encode("utf-8")
    model_sha256 = sha256(source_bytes).hexdigest()
    render_fingerprint = _render_fingerprint(model_spec_fingerprint, model_sha256)
    render_id = _new_render_id()

    generated_root = _artifact_root(workspace)
    render_dir = generated_root / render_id
    try:
        generated_root.mkdir(parents=True, exist_ok=True)
        render_dir.mkdir(exist_ok=False)
    except FileExistsError as exc:
        raise FemCoreError(
            "OPENSEES_RENDER_ARTIFACT_EXISTS",
            "OpenSees renderer will not overwrite an existing render artifact directory",
            details={"renderId": render_id},
        ) from exc
    except OSError as exc:
        raise FemCoreError(
            "OPENSEES_RENDER_WRITE_FAILED",
            "Unable to create the OpenSees generated-model artifact directory",
            details={"renderId": render_id},
        ) from exc

    model_path = render_dir / "model.py"
    manifest_path = render_dir / "render_manifest.json"
    report = {
        "schema": RENDER_SCHEMA,
        "status": "RENDERED",
        "renderId": render_id,
        "renderer": {"name": RENDERER_NAME, "version": RENDERER_VERSION},
        "input": {
            "modelSpecFingerprint": model_spec_fingerprint,
            "readinessProfile": SUPPORTED_READINESS_PROFILE,
            "units": dict(normalized["units"]),
        },
        "mapping": {
            "nodeTagPolicy": "IDENTITY",
            "elementTagPolicy": "IDENTITY",
            "geomTransfTag": _GEOM_TRANSF_TAG,
            "nodeCount": len(normalized["nodes"]),
            "elementCount": len(normalized["elements"]),
        },
        "artifacts": {
            "modelPath": workspace_relative_path(workspace, model_path),
            "modelSha256": model_sha256,
            "manifestPath": workspace_relative_path(workspace, manifest_path),
        },
        "renderFingerprint": render_fingerprint,
    }

    try:
        _write_text(model_path, source)
        _write_text(
            manifest_path,
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
    except OSError as exc:
        shutil.rmtree(render_dir, ignore_errors=True)
        raise FemCoreError(
            "OPENSEES_RENDER_WRITE_FAILED",
            "Unable to publish the OpenSees generated-model artifact bundle",
            details={"renderId": render_id},
        ) from exc

    return report
