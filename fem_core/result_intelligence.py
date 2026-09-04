from __future__ import annotations

import csv
import json
import math
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import Any

from fem_core.ansys_result_reader import describe_ansys_binary_result, query_ansys_nodal_result
from fem_core.errors import FemCoreError
from fem_core.pathing import resolve_workspace_file, workspace_relative_path

_OPEN_SEES_RESPONSE_COLUMNS = (
    "time_s",
    "relative_displacement_m",
    "relative_velocity_m_s",
    "relative_acceleration_m_s2",
)
_ARTIFACT_HASH_PAIRS = (
    ("responseCsv", "responseSha256"),
    ("resultSummary", "resultSummarySha256"),
    ("solverLog", "solverLogSha256"),
    ("runtimeOutput", "runtimeOutputSha256"),
    ("binaryResult", "binaryResultSha256"),
)
_COMPONENT_ALIASES = {
    "X": "X",
    "UX": "X",
    "U1": "X",
    "1": "X",
    "Y": "Y",
    "UY": "Y",
    "U2": "Y",
    "2": "Y",
    "Z": "Z",
    "UZ": "Z",
    "U3": "Z",
    "3": "Z",
}
_ANSYS_DOF_TO_AXIS = {"UX": "X", "UY": "Y", "UZ": "Z"}
_MAX_RESULT_SERIES_SAMPLES = 5000


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _workspace_candidate(workspace: Path, raw_path: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise FemCoreError("INVALID_PATH", "A non-empty result run reference is required")
    root = workspace.resolve()
    requested = Path(raw_path)
    candidate = requested.resolve() if requested.is_absolute() else (root / requested).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise FemCoreError(
            "PATH_OUTSIDE_WORKSPACE",
            "Result Intelligence may only access paths inside the active workspace",
            details={"path": raw_path},
        ) from exc
    return candidate


def _resolve_run_manifest(workspace: Path, run_ref: str) -> Path:
    if run_ref.startswith("run_") and "/" not in run_ref and "\\" not in run_ref:
        candidate = _workspace_candidate(workspace, f".femagent/runs/{run_ref}/run_manifest.json")
    else:
        candidate = _workspace_candidate(workspace, run_ref)
        if candidate.is_dir():
            candidate = candidate / "run_manifest.json"
    if not candidate.exists():
        raise FemCoreError(
            "RUN_MANIFEST_NOT_FOUND",
            "The requested FEM run manifest does not exist",
            details={"runRef": run_ref},
        )
    if not candidate.is_file():
        raise FemCoreError("INVALID_RUN_MANIFEST", "The resolved run manifest path is not a file")
    return candidate


def _load_run_manifest(workspace: Path, run_ref: str) -> tuple[Path, dict[str, Any]]:
    path = _resolve_run_manifest(workspace, run_ref)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FemCoreError("INVALID_RUN_MANIFEST", "Run manifest is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise FemCoreError("INVALID_RUN_MANIFEST", "Run manifest must be a JSON object")
    required = {
        "kind": "solver_run",
        "schemaVersion": "1.0",
        "status": "COMPLETED",
    }
    if any(payload.get(key) != expected for key, expected in required.items()):
        raise FemCoreError(
            "INVALID_RUN_MANIFEST",
            "Result Intelligence requires a completed FEMagent solver_run manifest",
            details={"receivedKind": payload.get("kind"), "receivedStatus": payload.get("status")},
        )
    run_id = payload.get("runId")
    case_fingerprint = payload.get("caseFingerprint")
    solver = payload.get("solver")
    outputs = payload.get("outputs")
    if not isinstance(run_id, str) or not run_id.startswith("run_"):
        raise FemCoreError("INVALID_RUN_MANIFEST", "Run manifest has an invalid runId")
    if not isinstance(case_fingerprint, str) or len(case_fingerprint) != 64:
        raise FemCoreError("INVALID_RUN_MANIFEST", "Run manifest has an invalid caseFingerprint")
    if not isinstance(solver, dict) or not isinstance(solver.get("name"), str):
        raise FemCoreError("INVALID_RUN_MANIFEST", "Run manifest is missing solver identity")
    if not isinstance(outputs, dict):
        raise FemCoreError("INVALID_RUN_MANIFEST", "Run manifest outputs must be a JSON object")
    return path, payload


def _verify_declared_artifacts(workspace: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    outputs = manifest["outputs"]
    artifacts: list[dict[str, Any]] = []
    for path_key, hash_key in _ARTIFACT_HASH_PAIRS:
        raw_path = outputs.get(path_key)
        declared_hash = outputs.get(hash_key)
        if raw_path is None and declared_hash is None:
            continue
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise FemCoreError(
                "INVALID_RUN_MANIFEST",
                "Run manifest declares a result artifact hash without a valid path",
                details={"pathKey": path_key, "hashKey": hash_key},
            )
        path = resolve_workspace_file(workspace, raw_path)
        actual_hash = _sha256_file(path)
        if declared_hash is not None:
            if not isinstance(declared_hash, str) or len(declared_hash) != 64:
                raise FemCoreError(
                    "INVALID_RUN_MANIFEST",
                    "Run manifest contains an invalid artifact SHA256",
                    details={"path": raw_path, "hashKey": hash_key},
                )
            if actual_hash.lower() != declared_hash.lower():
                raise FemCoreError(
                    "RESULT_ARTIFACT_HASH_MISMATCH",
                    "Recorded result artifact does not match its declared SHA256",
                    details={
                        "path": raw_path,
                        "declaredSha256": declared_hash,
                        "actualSha256": actual_hash,
                    },
                )
        artifacts.append(
            {
                "role": path_key,
                "path": workspace_relative_path(workspace, path),
                "sha256": actual_hash,
                "declaredSha256": declared_hash,
                "status": "VERIFIED" if declared_hash is not None else "PRESENT_UNHASHED",
            }
        )
    return artifacts


def _finite(value: str, *, column: str, row_number: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FemCoreError(
            "INVALID_RESULT_SERIES",
            "OpenSees response CSV contains a non-numeric value",
            details={"column": column, "row": row_number},
        ) from exc
    if not math.isfinite(number):
        raise FemCoreError(
            "INVALID_RESULT_SERIES",
            "OpenSees response CSV contains a non-finite value",
            details={"column": column, "row": row_number},
        )
    return number


def _read_open_sees_response(path: Path) -> dict[str, list[float]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != _OPEN_SEES_RESPONSE_COLUMNS:
                raise FemCoreError(
                    "UNSUPPORTED_RESULT_SERIES",
                    "OpenSees response CSV does not match FEMagent's controlled response schema",
                    details={
                        "expected": list(_OPEN_SEES_RESPONSE_COLUMNS),
                        "received": reader.fieldnames,
                    },
                )
            columns = {name: [] for name in _OPEN_SEES_RESPONSE_COLUMNS}
            for row_number, row in enumerate(reader, start=2):
                for name in _OPEN_SEES_RESPONSE_COLUMNS:
                    columns[name].append(_finite(row.get(name, ""), column=name, row_number=row_number))
    except UnicodeDecodeError as exc:
        raise FemCoreError("INVALID_RESULT_SERIES", "OpenSees response CSV must be UTF-8") from exc
    if not columns["time_s"]:
        raise FemCoreError("INVALID_RESULT_SERIES", "OpenSees response CSV contains no samples")
    times = columns["time_s"]
    if any(current <= previous for previous, current in pairwise(times)):
        raise FemCoreError(
            "INVALID_RESULT_SERIES",
            "OpenSees response time must be strictly increasing",
        )
    return columns


def _open_sees_result_manifest(
    workspace: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    outputs = manifest["outputs"]
    response_path = outputs.get("responseCsv")
    summary = manifest.get("summary") if isinstance(manifest.get("summary"), dict) else {}
    warnings: list[dict[str, Any]] = []
    if not isinstance(response_path, str):
        warnings.append(
            {
                "code": "NO_STANDARD_RESPONSE_SERIES",
                "message": "This OpenSees run did not record a FEMagent standard response series",
            }
        )
        return {
            "integrityStatus": "LIMITED",
            "abscissa": None,
            "queryCapabilities": [],
            "warnings": warnings,
            "observations": summary,
        }

    response_file = resolve_workspace_file(workspace, response_path)
    series = _read_open_sees_response(response_file)
    response_node = summary.get("responseNode")
    response_dof = summary.get("responseDof")
    if not isinstance(response_node, int) or response_dof != 1:
        raise FemCoreError(
            "INVALID_RESULT_SERIES",
            "Controlled OpenSees response is missing its recorded node/DOF identity",
        )
    capabilities = [
        {
            "quantity": "DISPLACEMENT",
            "component": "X",
            "target": {"type": "NODE", "id": response_node},
            "unit": "m",
            "referenceFrame": "RELATIVE",
            "sourceColumn": "relative_displacement_m",
        },
        {
            "quantity": "VELOCITY",
            "component": "X",
            "target": {"type": "NODE", "id": response_node},
            "unit": "m/s",
            "referenceFrame": "RELATIVE",
            "sourceColumn": "relative_velocity_m_s",
        },
        {
            "quantity": "ACCELERATION",
            "component": "X",
            "target": {"type": "NODE", "id": response_node},
            "unit": "m/s2",
            "referenceFrame": "RELATIVE",
            "sourceColumn": "relative_acceleration_m_s2",
        },
    ]
    return {
        "integrityStatus": "VALID",
        "abscissa": {
            "semantic": "TIME",
            "unit": "s",
            "sampleCount": len(series["time_s"]),
            "start": series["time_s"][0],
            "end": series["time_s"][-1],
        },
        "queryCapabilities": capabilities,
        "warnings": warnings,
        "observations": summary,
    }


def _ansys_result_manifest(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    outputs = manifest["outputs"]
    binary_path = outputs.get("binaryResult")
    summary = manifest.get("summary") if isinstance(manifest.get("summary"), dict) else {}
    if not isinstance(binary_path, str):
        return {
            "integrityStatus": "LIMITED",
            "abscissa": None,
            "queryCapabilities": [],
            "warnings": [
                {
                    "code": "ANSYS_BINARY_RESULT_NOT_RECORDED",
                    "message": "This ANSYS run did not record a MAPDL binary result artifact",
                }
            ],
            "observations": summary,
        }

    binary_file = resolve_workspace_file(workspace, binary_path)
    description = describe_ansys_binary_result(binary_file)
    axes = [
        _ANSYS_DOF_TO_AXIS[dof]
        for dof in description["dofLabels"]
        if dof in _ANSYS_DOF_TO_AXIS
    ]
    capabilities = [
        {
            "quantity": quantity,
            "component": axis,
            "target": {"type": "NODE", "selection": "RECORDED_NODE_IDS"},
            "unit": None,
            "referenceFrame": "SOLVER_NATIVE",
            "sourceArtifact": workspace_relative_path(workspace, binary_file),
        }
        for quantity in description["quantities"]
        for axis in axes
    ]
    return {
        "integrityStatus": "VALID",
        "abscissa": description["abscissa"],
        "queryCapabilities": capabilities,
        "warnings": [
            {
                "code": "ANSYS_RESULT_UNIT_SYSTEM_NOT_DECLARED",
                "message": (
                    "MAPDL binary results are solver-native; PR9 does not infer physical units "
                    "or interpret result-set abscissa values as seconds"
                ),
            }
        ],
        "observations": {**summary, "binaryResult": description},
    }


def inspect_result(workspace: Path, run_ref: str) -> dict[str, Any]:
    manifest_path, manifest = _load_run_manifest(workspace, run_ref)
    artifacts = _verify_declared_artifacts(workspace, manifest)
    solver = manifest["solver"]
    solver_name = str(solver["name"]).upper()

    if solver_name == "OPENSEESPY":
        details = _open_sees_result_manifest(workspace, manifest)
    elif solver_name == "ANSYS":
        details = _ansys_result_manifest(workspace, manifest)
    else:
        details = {
            "integrityStatus": "LIMITED",
            "abscissa": None,
            "queryCapabilities": [],
            "warnings": [
                {
                    "code": "RESULT_READER_NOT_AVAILABLE",
                    "message": f"PR9 result reader is not available for solver {solver_name}",
                }
            ],
            "observations": manifest.get("summary") if isinstance(manifest.get("summary"), dict) else {},
        }

    return {
        "schemaVersion": "1.0",
        "kind": "result_manifest",
        "runId": manifest["runId"],
        "caseFingerprint": manifest["caseFingerprint"],
        "runManifest": workspace_relative_path(workspace, manifest_path),
        "solver": solver,
        "integrity": {
            "status": details["integrityStatus"],
            "artifacts": artifacts,
        },
        "abscissa": details["abscissa"],
        "queryCapabilities": details["queryCapabilities"],
        "observations": details["observations"],
        "warnings": details["warnings"],
    }


def _normalized_component(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FemCoreError("INVALID_RESULT_QUERY", "Result query component must be a non-empty string")
    normalized = _COMPONENT_ALIASES.get(value.strip().upper())
    if normalized is None:
        raise FemCoreError(
            "INVALID_RESULT_QUERY",
            "Result query component is not a supported Cartesian alias",
            details={"component": value},
        )
    return normalized


def _validated_query(query: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(query, dict):
        raise FemCoreError("INVALID_RESULT_QUERY", "Result query must be a JSON object")
    quantity = query.get("quantity")
    operation = query.get("operation")
    target = query.get("target")
    if not isinstance(quantity, str) or not quantity.strip():
        raise FemCoreError("INVALID_RESULT_QUERY", "Result query quantity must be a non-empty string")
    if not isinstance(operation, str) or operation.strip().upper() not in {"SUMMARY", "SERIES"}:
        raise FemCoreError("INVALID_RESULT_QUERY", "Result query operation must be SUMMARY or SERIES")
    if not isinstance(target, dict) or str(target.get("type") or "").upper() != "NODE":
        raise FemCoreError("INVALID_RESULT_QUERY", "PR9 result queries require a NODE target")
    target_id = target.get("id")
    if not isinstance(target_id, int) or isinstance(target_id, bool) or target_id <= 0:
        raise FemCoreError("INVALID_RESULT_QUERY", "Result query node id must be a positive integer")
    offset = query.get("offset", 0)
    limit = query.get("limit", 500)
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise FemCoreError("INVALID_RESULT_QUERY", "Result query offset must be a non-negative integer")
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or limit <= 0
        or limit > _MAX_RESULT_SERIES_SAMPLES
    ):
        raise FemCoreError(
            "INVALID_RESULT_QUERY",
            f"Result query limit must be between 1 and {_MAX_RESULT_SERIES_SAMPLES}",
        )
    return {
        "quantity": quantity.strip().upper(),
        "operation": operation.strip().upper(),
        "target": {"type": "NODE", "id": target_id},
        "component": _normalized_component(query.get("component")),
        "offset": offset,
        "limit": limit,
    }


def _matching_capability(result_manifest: dict[str, Any], query: dict[str, Any]) -> dict[str, Any]:
    for capability in result_manifest["queryCapabilities"]:
        if (
            capability.get("quantity") == query["quantity"]
            and capability.get("component") == query["component"]
            and capability.get("target") == query["target"]
        ):
            return capability
    raise FemCoreError(
        "RESULT_SERIES_UNAVAILABLE",
        "The recorded run does not contain the requested result series",
        details={
            "quantity": query["quantity"],
            "component": query["component"],
            "target": query["target"],
        },
    )


def _base_query_response(
    result_manifest: dict[str, Any],
    normalized: dict[str, Any],
    *,
    unit: str | None,
    reference_frame: str,
    abscissa_semantic: str,
    abscissa_unit: str | None,
    source: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "kind": "result_query",
        "runId": result_manifest["runId"],
        "caseFingerprint": result_manifest["caseFingerprint"],
        "solver": result_manifest["solver"],
        "quantity": normalized["quantity"],
        "target": normalized["target"],
        "component": normalized["component"],
        "operation": normalized["operation"],
        "unit": unit,
        "referenceFrame": reference_frame,
        "abscissa": {"semantic": abscissa_semantic, "unit": abscissa_unit},
        "source": source,
    }


def _attach_summary_or_series(
    response: dict[str, Any],
    normalized: dict[str, Any],
    *,
    abscissa: list[float],
    values: list[float],
) -> dict[str, Any]:
    if not values or len(abscissa) != len(values):
        raise FemCoreError(
            "INVALID_RESULT_SERIES",
            "Result query requires matching non-empty abscissa and value series",
            details={"abscissaCount": len(abscissa), "valueCount": len(values)},
        )
    if normalized["operation"] == "SUMMARY":
        peak_index = max(range(len(values)), key=lambda index: abs(values[index]))
        response["summary"] = {
            "sampleCount": len(values),
            "min": min(values),
            "max": max(values),
            "absolutePeak": abs(values[peak_index]),
            "abscissaAtAbsolutePeak": abscissa[peak_index],
        }
        return response

    offset = normalized["offset"]
    limit = normalized["limit"]
    end = min(offset + limit, len(values))
    response["series"] = [
        {"abscissa": abscissa[index], "value": values[index]}
        for index in range(offset, end)
    ]
    response["paging"] = {
        "offset": offset,
        "limit": limit,
        "returned": max(0, end - offset),
        "total": len(values),
    }
    return response


def _query_open_sees(
    workspace: Path,
    run_manifest: dict[str, Any],
    result_manifest: dict[str, Any],
    normalized: dict[str, Any],
) -> dict[str, Any]:
    capability = _matching_capability(result_manifest, normalized)
    response_path = run_manifest["outputs"].get("responseCsv")
    if not isinstance(response_path, str):
        raise FemCoreError(
            "RESULT_SERIES_UNAVAILABLE",
            "This OpenSees run did not record a standard response series",
        )
    response_file = resolve_workspace_file(workspace, response_path)
    series = _read_open_sees_response(response_file)
    source_column = str(capability["sourceColumn"])
    response = _base_query_response(
        result_manifest,
        normalized,
        unit=capability.get("unit"),
        reference_frame=str(capability.get("referenceFrame")),
        abscissa_semantic="TIME",
        abscissa_unit="s",
        source={
            "artifact": workspace_relative_path(workspace, response_file),
            "column": source_column,
        },
    )
    return _attach_summary_or_series(
        response,
        normalized,
        abscissa=series["time_s"],
        values=series[source_column],
    )


def _query_ansys(
    workspace: Path,
    run_manifest: dict[str, Any],
    result_manifest: dict[str, Any],
    normalized: dict[str, Any],
) -> dict[str, Any]:
    binary_path = run_manifest["outputs"].get("binaryResult")
    if not isinstance(binary_path, str):
        raise FemCoreError(
            "RESULT_SERIES_UNAVAILABLE",
            "This ANSYS run did not record a MAPDL binary result artifact",
        )
    binary_file = resolve_workspace_file(workspace, binary_path)
    data = query_ansys_nodal_result(
        binary_file,
        quantity=normalized["quantity"],
        node_id=normalized["target"]["id"],
        component=normalized["component"],
    )
    response = _base_query_response(
        result_manifest,
        normalized,
        unit=data["unit"],
        reference_frame=data["referenceFrame"],
        abscissa_semantic=data["abscissaSemantic"],
        abscissa_unit=data["abscissaUnit"],
        source={"artifact": workspace_relative_path(workspace, binary_file)},
    )
    return _attach_summary_or_series(
        response,
        normalized,
        abscissa=data["abscissaValues"],
        values=data["values"],
    )


def query_result(workspace: Path, run_ref: str, query: dict[str, Any]) -> dict[str, Any]:
    normalized = _validated_query(query)
    result_manifest = inspect_result(workspace, run_ref)
    _, run_manifest = _load_run_manifest(workspace, run_ref)
    solver_name = str(run_manifest["solver"]["name"]).upper()
    if solver_name == "OPENSEESPY":
        return _query_open_sees(workspace, run_manifest, result_manifest, normalized)
    if solver_name == "ANSYS":
        return _query_ansys(workspace, run_manifest, result_manifest, normalized)
    raise FemCoreError(
        "RESULT_SERIES_UNAVAILABLE",
        "The requested solver result reader does not expose this series",
        details={"solver": solver_name},
    )
