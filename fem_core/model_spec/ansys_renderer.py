from __future__ import annotations

import json
import shutil
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model
from fem_core.model_spec.readiness import evaluate_engineering_model_readiness
from fem_core.model_spec.validator import validate_engineering_model_spec
from fem_core.pathing import resolve_workspace_file, workspace_relative_path

RENDER_SCHEMA = "FEMAGENT_ANSYS_MODEL_RENDER_V1"
RENDERER_NAME = "ANSYS_FRAME_2D_BEAM3_V1"
RENDERER_VERSION = "1.0"
SUPPORTED_READINESS_PROFILE = "FRAME_2D_ELASTIC_READINESS_V1"
_FRAME_ELEMENT_TYPE_ID = 1
_MASS_ELEMENT_TYPE_ID = 2


def _new_render_id() -> str:
    return f"ansys_render_{uuid4().hex[:16]}"


def _format_number(value: Any) -> str:
    return format(float(value), ".15g")


def _artifact_root(workspace: Path) -> Path:
    root = workspace.resolve()
    generated = (root / ".femagent" / "generated-models").resolve()
    try:
        generated.relative_to(root)
    except ValueError as exc:
        raise FemCoreError(
            "ANSYS_MODEL_RENDER_WRITE_FAILED",
            "Generated ANSYS model directory resolves outside the active workspace",
        ) from exc
    return generated


def _mass_mapping(normalized: dict[str, Any]) -> list[dict[str, int]]:
    masses = normalized["nodalMasses"]
    max_element_id = max(int(item["id"]) for item in normalized["elements"])
    max_section_id = max(int(item["id"]) for item in normalized["sections"])
    mapping: list[dict[str, int]] = []
    for offset, mass in enumerate(masses, start=1):
        mapping.append(
            {
                "nodeId": int(mass["nodeId"]),
                "elementId": max_element_id + offset,
                "realConstantId": max_section_id + offset,
            }
        )
    return mapping


def build_ansys_frame_2d_source(
    normalized: dict[str, Any],
    *,
    model_spec_fingerprint: str,
) -> tuple[str, list[dict[str, int]]]:
    mass_mapping = _mass_mapping(normalized)
    lines = [
        "! FEMagent deterministic EngineeringModelSpec V1 -> ANSYS MAPDL",
        f"! modelSpecFingerprint={model_spec_fingerprint}",
        (
            "! units="
            f"{normalized['units']['length']},"
            f"{normalized['units']['force']},"
            f"{normalized['units']['time']}"
        ),
        "/PREP7",
        f"ET,{_FRAME_ELEMENT_TYPE_ID},BEAM3",
    ]
    if mass_mapping:
        lines.extend(
            [
                f"ET,{_MASS_ELEMENT_TYPE_ID},MASS21",
                f"KEYOPT,{_MASS_ELEMENT_TYPE_ID},3,0",
            ]
        )

    lines.append("! materials")
    for material in normalized["materials"]:
        lines.append(
            "MP,EX,"
            f"{int(material['id'])},"
            f"{_format_number(material['youngsModulus'])}"
        )

    lines.append("! frame sections: BEAM3 AREA, IZZ only")
    for section in normalized["sections"]:
        lines.append(
            "R,"
            f"{int(section['id'])},"
            f"{_format_number(section['area'])},"
            f"{_format_number(section['iz'])}"
        )

    lines.append("! nodes")
    for node in normalized["nodes"]:
        lines.append(
            "N,"
            f"{int(node['id'])},"
            f"{_format_number(node['x'])},"
            f"{_format_number(node['y'])},0"
        )

    lines.append("! frame elements")
    for element in normalized["elements"]:
        lines.extend(
            [
                f"TYPE,{_FRAME_ELEMENT_TYPE_ID}",
                f"MAT,{int(element['materialId'])}",
                f"REAL,{int(element['sectionId'])}",
                (
                    "EN,"
                    f"{int(element['id'])},"
                    f"{int(element['nodeI'])},"
                    f"{int(element['nodeJ'])}"
                ),
            ]
        )

    if mass_mapping:
        mass_by_node = {
            int(item["nodeId"]): item
            for item in normalized["nodalMasses"]
        }
        lines.append("! concentrated nodal translational masses")
        for mapping in mass_mapping:
            mass = mass_by_node[mapping["nodeId"]]
            lines.extend(
                [
                    f"TYPE,{_MASS_ELEMENT_TYPE_ID}",
                    (
                        "R,"
                        f"{mapping['realConstantId']},"
                        f"{_format_number(mass['mUX'])},"
                        f"{_format_number(mass['mUY'])},0,0,0,0"
                    ),
                    f"REAL,{mapping['realConstantId']}",
                    f"EN,{mapping['elementId']},{mapping['nodeId']}",
                    f"D,{mapping['nodeId']},UZ,0",
                    f"D,{mapping['nodeId']},ROTX,0",
                    f"D,{mapping['nodeId']},ROTY,0",
                ]
            )

    lines.append("! ModelSpec constraints")
    dof_map = {"UX": "UX", "UY": "UY", "RZ": "ROTZ"}
    for constraint in normalized["constraints"]:
        node_id = int(constraint["nodeId"])
        for dof in constraint["dofs"]:
            lines.append(f"D,{node_id},{dof_map[str(dof)]},0")

    lines.extend(
        [
            "FINISH",
            "! Controlled PR29 injection scaffold; no load/damping/time controls here",
            "/SOLU",
            "ANTYPE,TRANS",
            "SOLVE",
            "FINISH",
            "/EXIT,NOSAVE",
        ]
    )
    return "\n".join(lines) + "\n", mass_mapping


def _render_fingerprint(
    *,
    model_spec_fingerprint: str,
    model_sha256: str,
) -> str:
    payload = {
        "rendererName": RENDERER_NAME,
        "rendererVersion": RENDERER_VERSION,
        "modelSpecFingerprint": model_spec_fingerprint,
        "modelSha256": model_sha256,
    }
    return sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


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


def render_ansys_frame_2d(
    workspace: Path,
    spec: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise FemCoreError(
            "ANSYS_MODEL_RENDER_SPEC_NOT_OBJECT",
            "ANSYS renderer requires a ModelSpec JSON object",
        )

    readiness = evaluate_engineering_model_readiness(spec)
    if readiness["status"] != "READY":
        return _blocked_result(readiness)
    if readiness.get("profile") != SUPPORTED_READINESS_PROFILE:
        raise FemCoreError(
            "ANSYS_MODEL_RENDER_UNSUPPORTED_PROFILE",
            "ANSYS Frame 2D renderer received an unsupported readiness profile",
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
            "ANSYS_MODEL_RENDER_INTERNAL_INVARIANT",
            "Readiness and ModelSpec validation disagree at the ANSYS renderer boundary",
        )

    source, mass_mapping = build_ansys_frame_2d_source(
        normalized,
        model_spec_fingerprint=model_spec_fingerprint,
    )
    source_bytes = source.encode("utf-8")
    model_sha256 = sha256(source_bytes).hexdigest()
    render_id = _new_render_id()

    generated_root = _artifact_root(workspace)
    render_dir = generated_root / render_id
    try:
        generated_root.mkdir(parents=True, exist_ok=True)
        render_dir.mkdir(exist_ok=False)
    except FileExistsError as exc:
        raise FemCoreError(
            "ANSYS_MODEL_RENDER_ARTIFACT_EXISTS",
            "ANSYS renderer will not overwrite an existing render artifact directory",
            details={"renderId": render_id},
        ) from exc
    except OSError as exc:
        raise FemCoreError(
            "ANSYS_MODEL_RENDER_WRITE_FAILED",
            "Unable to create the ANSYS generated-model artifact directory",
            details={"renderId": render_id},
        ) from exc

    model_path = render_dir / "model.inp"
    manifest_path = render_dir / "render_manifest.json"
    try:
        model_path.write_text(source, encoding="utf-8")
        inspection = inspect_model(
            workspace,
            workspace_relative_path(workspace, model_path),
        )
        bundle = inspection.get("bundle")
        bundle_fingerprint = (
            bundle.get("bundleFingerprint")
            if isinstance(bundle, dict)
            else None
        )
        if (
            inspection.get("format") != "ANSYS_APDL_TEXT"
            or inspection.get("validation", {}).get("executionEligibility")
            != "STATICALLY_ELIGIBLE"
            or not isinstance(bundle_fingerprint, str)
        ):
            raise FemCoreError(
                "ANSYS_MODEL_RENDER_INTERNAL_INVARIANT",
                "Rendered ANSYS source did not pass deterministic static inspection",
                details={"inspection": inspection},
            )

        render_fingerprint = _render_fingerprint(
            model_spec_fingerprint=model_spec_fingerprint,
            model_sha256=model_sha256,
        )
        report = {
            "schema": RENDER_SCHEMA,
            "status": "RENDERED",
            "renderId": render_id,
            "renderer": {
                "name": RENDERER_NAME,
                "version": RENDERER_VERSION,
                "elementMapping": "BEAM3_PLANAR_EULER_BERNOULLI",
                "massMapping": "MASS21_EXPLICIT_MASSX_MASSY",
            },
            "input": {
                "modelSpecFingerprint": model_spec_fingerprint,
                "readinessProfile": SUPPORTED_READINESS_PROFILE,
                "units": dict(normalized["units"]),
            },
            "mapping": {
                "nodeTagPolicy": "IDENTITY",
                "frameElementTagPolicy": "IDENTITY",
                "materialIdPolicy": "IDENTITY",
                "sectionRealConstantIdPolicy": "IDENTITY",
                "frameElementTypeId": _FRAME_ELEMENT_TYPE_ID,
                "massElementTypeId": (
                    _MASS_ELEMENT_TYPE_ID if mass_mapping else None
                ),
                "auxiliaryMassElements": mass_mapping,
                "nodeCount": len(normalized["nodes"]),
                "frameElementCount": len(normalized["elements"]),
            },
            "executionScaffold": {
                "profile": "ANSYS_TRANSIENT_INJECTION_HOOK_V1",
                "analysisCommand": "ANTYPE,TRANS",
                "solveCommand": "SOLVE",
                "ownsLoad": False,
                "ownsDamping": False,
                "ownsTimeControls": False,
            },
            "artifacts": {
                "modelPath": workspace_relative_path(workspace, model_path),
                "modelSha256": model_sha256,
                "bundleFingerprint": bundle_fingerprint,
                "manifestPath": workspace_relative_path(
                    workspace,
                    manifest_path,
                ),
            },
            "renderFingerprint": render_fingerprint,
        }
        manifest_path.write_text(
            json.dumps(
                report,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    except (FemCoreError, OSError):
        shutil.rmtree(render_dir, ignore_errors=True)
        raise

    return report


def verify_ansys_model_render(
    workspace: Path,
    *,
    model_path: str,
    manifest_path: str,
    expected_model_spec_fingerprint: str | None = None,
) -> dict[str, Any]:
    manifest_file = resolve_workspace_file(workspace, manifest_path)
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FemCoreError(
            "ANSYS_MODEL_RENDER_MANIFEST_INVALID",
            "ANSYS render manifest must be valid UTF-8 JSON",
        ) from exc

    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != RENDER_SCHEMA
        or manifest.get("status") != "RENDERED"
        or manifest.get("renderer", {}).get("name") != RENDERER_NAME
        or manifest.get("renderer", {}).get("version") != RENDERER_VERSION
    ):
        raise FemCoreError(
            "ANSYS_MODEL_RENDER_MANIFEST_INVALID",
            "ANSYS render manifest does not match the PR33 renderer contract",
        )

    rendered_model_path = manifest.get("artifacts", {}).get("modelPath")
    if rendered_model_path != model_path:
        raise FemCoreError(
            "ANSYS_MODEL_RENDER_PATH_MISMATCH",
            "ANSYS execution model path does not match the verified render manifest",
            details={
                "expected": rendered_model_path,
                "received": model_path,
            },
        )

    model_file = resolve_workspace_file(workspace, model_path)
    current_model_sha = sha256(model_file.read_bytes()).hexdigest()
    expected_model_sha = manifest.get("artifacts", {}).get("modelSha256")
    if current_model_sha != expected_model_sha:
        raise FemCoreError(
            "ANSYS_MODEL_RENDER_SOURCE_HASH_MISMATCH",
            "Rendered ANSYS model source changed after deterministic rendering",
            details={
                "expected": expected_model_sha,
                "actual": current_model_sha,
            },
        )

    inspection = inspect_model(workspace, model_path)
    bundle = inspection.get("bundle")
    current_bundle_fingerprint = (
        bundle.get("bundleFingerprint")
        if isinstance(bundle, dict)
        else None
    )
    expected_bundle_fingerprint = manifest.get("artifacts", {}).get(
        "bundleFingerprint"
    )
    if current_bundle_fingerprint != expected_bundle_fingerprint:
        raise FemCoreError(
            "ANSYS_MODEL_RENDER_BUNDLE_MISMATCH",
            "Current ANSYS Model Bundle no longer matches the render manifest",
            details={
                "expected": expected_bundle_fingerprint,
                "actual": current_bundle_fingerprint,
            },
        )

    model_spec_fingerprint = manifest.get("input", {}).get(
        "modelSpecFingerprint"
    )
    if (
        expected_model_spec_fingerprint is not None
        and model_spec_fingerprint != expected_model_spec_fingerprint
    ):
        raise FemCoreError(
            "ANSYS_MODEL_RENDER_MODEL_SPEC_MISMATCH",
            "ANSYS render manifest is bound to a different EngineeringModelSpec",
            details={
                "expected": expected_model_spec_fingerprint,
                "received": model_spec_fingerprint,
            },
        )

    expected_render_fingerprint = _render_fingerprint(
        model_spec_fingerprint=str(model_spec_fingerprint),
        model_sha256=current_model_sha,
    )
    if manifest.get("renderFingerprint") != expected_render_fingerprint:
        raise FemCoreError(
            "ANSYS_MODEL_RENDER_FINGERPRINT_MISMATCH",
            "ANSYS render fingerprint does not recompute from current deterministic identities",
        )

    mapping = manifest.get("mapping")
    if (
        not isinstance(mapping, dict)
        or mapping.get("nodeTagPolicy") != "IDENTITY"
        or mapping.get("frameElementTagPolicy") != "IDENTITY"
    ):
        raise FemCoreError(
            "ANSYS_MODEL_RENDER_MAPPING_UNPROVEN",
            "ANSYS render manifest does not prove identity node/frame-element mapping",
        )

    return {
        "schema": "FEMAGENT_ANSYS_MODEL_RENDER_VERIFICATION_V1",
        "status": "VERIFIED",
        "renderer": dict(manifest["renderer"]),
        "modelSpecFingerprint": model_spec_fingerprint,
        "units": copy_dict(manifest.get("input", {}).get("units")),
        "modelPath": model_path,
        "modelSha256": current_model_sha,
        "bundleFingerprint": current_bundle_fingerprint,
        "renderFingerprint": expected_render_fingerprint,
        "manifestPath": workspace_relative_path(workspace, manifest_file),
        "mapping": dict(mapping),
    }


def copy_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


__all__ = [
    "RENDERER_NAME",
    "RENDERER_VERSION",
    "RENDER_SCHEMA",
    "build_ansys_frame_2d_source",
    "render_ansys_frame_2d",
    "verify_ansys_model_render",
]
