from __future__ import annotations

import csv
import json
import math
from hashlib import sha256
from pathlib import Path
from typing import Any

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
    if any(current <= previous for previous, current in zip(times, times[1:])):
        raise FemCoreError(
            "INVALID_RESULT_SERIES",
            "OpenSees response time must be strictly increasing",
        )
    return columns


def _open_sees_result_manifest(
    workspace: Path,
    manifest: dict[str, Any],
    artifacts: list[dict[str, Any]],
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
    sample_count = len(series["time_s"])
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
            "sampleCount": sample_count,
            "start": series["time_s"][0],
            "end": series["time_s"][-1],
        },
        "queryCapabilities": capabilities,
        "warnings": warnings,
        "observations": summary,
    }


def inspect_result(workspace: Path, run_ref: str) -> dict[str, Any]:
    manifest_path, manifest = _load_run_manifest(workspace, run_ref)
    artifacts = _verify_declared_artifacts(workspace, manifest)
    solver = manifest["solver"]
    solver_name = str(solver["name"]).upper()

    if solver_name == "OPENSEESPY":
        details = _open_sees_result_manifest(workspace, manifest, artifacts)
    else:
        details = {
            "integrityStatus": "LIMITED",
            "abscissa": None,
            "queryCapabilities": [],
            "warnings": [
                {
                    "code": "RESULT_READER_NOT_AVAILABLE",
                    "message": f"PR9 result reader is not yet available for solver {solver_name}",
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
