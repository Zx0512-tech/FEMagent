from __future__ import annotations

import csv
import importlib.util
import json
import math
import subprocess
import sys
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from itertools import pairwise
from pathlib import Path
from typing import Any
from uuid import uuid4

from fem_core.errors import FemCoreError
from fem_core.pathing import resolve_workspace_file, workspace_relative_path
from fem_core.solvers.base import SolverAdapter

MODEL_KIND = "FEMAGENT_OPENSEES_MODEL_SPEC"
MODEL_SCHEMA_VERSION = "1.0"
SUPPORTED_MODEL_TYPES = frozenset({"ELASTIC_SDOF"})
CANONICAL_LOAD_COLUMNS = (
    "time_s",
    "load_kind",
    "channel_id",
    "application_type",
    "target_type",
    "target_id",
    "component",
    "quantity",
    "value",
    "unit",
)
_COMPONENT_ALIASES = frozenset({"X", "UX", "U1", "1"})
_TIME_RTOL = 1.0e-8
_WORKER_TIMEOUT_S = 60.0


class OpenSeesAdapter(SolverAdapter):
    name = "opensees"

    def status(self) -> dict[str, Any]:
        available = _opensees_available()
        return {
            "schemaVersion": "1.0",
            "kind": "solver_status",
            "solver": "OPENSEESPY",
            "available": available,
            "package": "openseespy",
            "packageVersion": _package_version() if available else None,
            "engineVersion": None,
            "executionMode": "ISOLATED_WORKER_PROCESS",
            "capabilities": ["TRANSIENT_UNIFORM_EXCITATION", "ELASTIC_SDOF"] if available else [],
        }

    def preflight(self, workspace: Path, *, model_path: str, load_path: str) -> dict[str, Any]:
        model_file = resolve_workspace_file(workspace, model_path)
        load_file = resolve_workspace_file(workspace, load_path)
        model = read_opensees_model_spec(model_file)
        load = read_canonical_uniform_excitation(load_file)
        status = self.status()

        checks = [
            {
                "code": "SOLVER_AVAILABLE",
                "status": "PASSED" if status["available"] else "FAILED",
            },
            {"code": "MODEL_SPEC_SUPPORTED", "status": "PASSED"},
            {"code": "CANONICAL_LOAD_SUPPORTED", "status": "PASSED"},
            {"code": "UNIFORM_TIME_STEP", "status": "PASSED"},
        ]
        warnings: list[dict[str, Any]] = []
        steps_per_period = model["periodS"] / load["dtS"]
        if steps_per_period < 20.0:
            warnings.append(
                {
                    "code": "COARSE_TIME_STEP_FOR_MODEL_PERIOD",
                    "message": "The load time step provides fewer than 20 steps per elastic natural period",
                    "stepsPerPeriod": steps_per_period,
                }
            )

        return {
            "schemaVersion": "1.0",
            "kind": "solver_preflight",
            "solver": "OPENSEESPY",
            "status": "READY" if status["available"] else "BLOCKED",
            "checks": checks,
            "warnings": warnings,
            "model": {
                "path": workspace_relative_path(workspace, model_file),
                "sha256": _sha256_file(model_file),
                "modelType": model["modelType"],
                "name": model["name"],
                "massKg": model["massKg"],
                "stiffnessNPerM": model["stiffnessNPerM"],
                "dampingRatio": model["dampingRatio"],
                "naturalFrequencyHz": model["naturalFrequencyHz"],
                "periodS": model["periodS"],
            },
            "load": {
                "path": workspace_relative_path(workspace, load_file),
                "sha256": _sha256_file(load_file),
                "format": "FEMAGENT_LOAD_CSV_V1",
                "sampleCount": len(load["timesS"]),
                "dtS": load["dtS"],
                "timeStartS": load["timesS"][0],
                "timeEndS": load["timesS"][-1],
                "channelId": load["channelId"],
                "component": load["component"],
                "quantity": "ACCELERATION",
                "unit": "m/s2",
            },
            "executionEstimate": {"analysisSteps": len(load["timesS"]) - 1},
        }

    def run(self, workspace: Path, *, model_path: str, load_path: str) -> dict[str, Any]:
        preflight = self.preflight(workspace, model_path=model_path, load_path=load_path)
        if preflight["status"] != "READY":
            raise FemCoreError(
                "SOLVER_PREFLIGHT_FAILED",
                "OpenSees analysis cannot run because solver preflight is blocked",
                details={"checks": preflight["checks"]},
            )

        model_file = resolve_workspace_file(workspace, model_path)
        load_file = resolve_workspace_file(workspace, load_path)
        run_id = f"run_{uuid4().hex[:16]}"
        run_dir = (workspace.resolve() / ".femagent" / "runs" / run_id).resolve()
        run_dir.mkdir(parents=True, exist_ok=False)
        worker_result = run_dir / "worker_result.json"
        solver_log = run_dir / "solver.log"

        command = [
            sys.executable,
            "-m",
            "fem_core.solvers.opensees_worker",
            "--model",
            str(model_file),
            "--load",
            str(load_file),
            "--run-dir",
            str(run_dir),
            "--result",
            str(worker_result),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=_WORKER_TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise FemCoreError(
                "SOLVER_TIMEOUT",
                "OpenSees worker exceeded the PR5 execution timeout",
                details={"timeoutS": _WORKER_TIMEOUT_S, "runId": run_id},
            ) from exc

        native_log = "[stdout]\n" + completed.stdout + "\n[stderr]\n" + completed.stderr
        solver_log.write_text(native_log, encoding="utf-8")
        if completed.returncode != 0 or not worker_result.exists():
            raise FemCoreError(
                "OPENSEES_WORKER_FAILED",
                "The isolated OpenSees worker failed",
                details={
                    "runId": run_id,
                    "returnCode": completed.returncode,
                    "logPath": workspace_relative_path(workspace, solver_log),
                },
            )

        try:
            worker = json.loads(worker_result.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FemCoreError(
                "INVALID_SOLVER_RESULT",
                "OpenSees worker did not produce a valid result document",
                details={"runId": run_id},
            ) from exc
        if not isinstance(worker, dict) or worker.get("status") != "COMPLETED":
            raise FemCoreError(
                "INVALID_SOLVER_RESULT",
                "OpenSees worker result is incomplete",
                details={"runId": run_id},
            )

        response_path = run_dir / "response.csv"
        summary_path = run_dir / "result_summary.json"
        model_sha = _sha256_file(model_file)
        load_sha = _sha256_file(load_file)
        fingerprint_payload = json.dumps(
            {
                "solver": "OPENSEESPY",
                "packageVersion": worker.get("packageVersion"),
                "engineVersion": worker.get("engineVersion"),
                "modelSha256": model_sha,
                "loadSha256": load_sha,
                "analysis": "TRANSIENT_UNIFORM_EXCITATION",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        case_fingerprint = sha256(fingerprint_payload).hexdigest()
        manifest = {
            "schemaVersion": "1.0",
            "kind": "solver_run",
            "runId": run_id,
            "caseFingerprint": case_fingerprint,
            "status": "COMPLETED",
            "solver": {
                "name": "OPENSEESPY",
                "packageVersion": worker.get("packageVersion"),
                "engineVersion": worker.get("engineVersion"),
                "executionMode": "ISOLATED_WORKER_PROCESS",
            },
            "model": {"path": workspace_relative_path(workspace, model_file), "sha256": model_sha},
            "load": {"path": workspace_relative_path(workspace, load_file), "sha256": load_sha},
            "analysis": worker.get("analysis"),
            "summary": worker.get("summary"),
            "outputs": {
                "runManifest": workspace_relative_path(workspace, run_dir / "run_manifest.json"),
                "responseCsv": workspace_relative_path(workspace, response_path),
                "responseSha256": _sha256_file(response_path),
                "resultSummary": workspace_relative_path(workspace, summary_path),
                "resultSummarySha256": _sha256_file(summary_path),
                "solverLog": workspace_relative_path(workspace, solver_log),
                "solverLogSha256": _sha256_file(solver_log),
            },
        }
        manifest_path = run_dir / "run_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return manifest


def read_opensees_model_spec(path: Path) -> dict[str, Any]:
    if path.suffix.lower() != ".json":
        raise FemCoreError("UNSUPPORTED_OPENSEES_MODEL_SPEC", "PR5 OpenSees model spec must be JSON")
    if path.stat().st_size > 1024 * 1024:
        raise FemCoreError("OPENSEES_MODEL_SPEC_TOO_LARGE", "OpenSees model spec exceeds the 1 MiB PR5 limit")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FemCoreError("INVALID_OPENSEES_MODEL_SPEC", "OpenSees model spec is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise FemCoreError("INVALID_OPENSEES_MODEL_SPEC", "OpenSees model spec must be a JSON object")
    if raw.get("schemaVersion") != MODEL_SCHEMA_VERSION or raw.get("kind") != MODEL_KIND:
        raise FemCoreError(
            "INVALID_OPENSEES_MODEL_SPEC",
            "OpenSees model spec schema/kind is unsupported",
            details={"expectedKind": MODEL_KIND, "expectedSchemaVersion": MODEL_SCHEMA_VERSION},
        )
    model_type = str(raw.get("modelType") or "").upper()
    if model_type not in SUPPORTED_MODEL_TYPES:
        raise FemCoreError(
            "UNSUPPORTED_OPENSEES_MODEL_TYPE",
            "PR5 supports only the controlled ELASTIC_SDOF OpenSees model type",
            details={"modelType": raw.get("modelType")},
        )
    units = raw.get("units")
    expected_units = {"length": "m", "force": "N", "mass": "kg", "time": "s"}
    if units != expected_units:
        raise FemCoreError(
            "UNSUPPORTED_MODEL_UNITS",
            "PR5 ELASTIC_SDOF requires the explicit SI unit system m/N/kg/s",
            details={"expected": expected_units, "received": units},
        )
    mass = _positive_finite(raw.get("massKg"), "massKg")
    stiffness = _positive_finite(raw.get("stiffnessNPerM"), "stiffnessNPerM")
    damping = _finite(raw.get("dampingRatio"), "dampingRatio")
    if damping < 0.0 or damping >= 1.0:
        raise FemCoreError("INVALID_DAMPING_RATIO", "dampingRatio must be in [0, 1)")
    omega = math.sqrt(stiffness / mass)
    return {
        "name": str(raw.get("name") or path.stem),
        "modelType": model_type,
        "massKg": mass,
        "stiffnessNPerM": stiffness,
        "dampingRatio": damping,
        "naturalFrequencyHz": omega / (2.0 * math.pi),
        "periodS": 2.0 * math.pi / omega,
        "responseNode": 2,
        "responseDof": 1,
    }


def read_canonical_uniform_excitation(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != CANONICAL_LOAD_COLUMNS:
                raise FemCoreError(
                    "UNSUPPORTED_CANONICAL_LOAD",
                    "OpenSees PR5 requires FEMAGENT_LOAD_CSV_V1 column order",
                    details={"expected": list(CANONICAL_LOAD_COLUMNS), "received": reader.fieldnames},
                )
            rows = list(reader)
    except UnicodeDecodeError as exc:
        raise FemCoreError("INVALID_CANONICAL_LOAD", "Canonical load must be UTF-8 CSV") from exc
    if len(rows) < 2:
        raise FemCoreError("LOAD_TOO_SHORT", "OpenSees transient analysis requires at least two load samples")

    invariant_fields = {
        key: {str(row.get(key) or "").strip() for row in rows}
        for key in ("load_kind", "channel_id", "application_type", "component", "quantity", "unit")
    }
    if any(len(values) != 1 for values in invariant_fields.values()):
        raise FemCoreError("MULTI_CHANNEL_NOT_SUPPORTED", "PR5 OpenSees Golden Path accepts one canonical load channel")
    load_kind = next(iter(invariant_fields["load_kind"])).upper()
    application = next(iter(invariant_fields["application_type"])).upper()
    component = next(iter(invariant_fields["component"])).upper()
    quantity = next(iter(invariant_fields["quantity"])).upper()
    unit = next(iter(invariant_fields["unit"]))
    channel_id = next(iter(invariant_fields["channel_id"]))
    if load_kind != "EARTHQUAKE" or application != "UNIFORM_EXCITATION":
        raise FemCoreError(
            "UNSUPPORTED_LOAD_APPLICATION",
            "PR5 OpenSees Golden Path supports EARTHQUAKE + UNIFORM_EXCITATION only",
            details={"loadKind": load_kind, "applicationType": application},
        )
    if quantity != "ACCELERATION" or unit != "m/s2":
        raise FemCoreError(
            "UNSUPPORTED_LOAD_QUANTITY",
            "OpenSees uniform excitation requires canonical ACCELERATION in m/s2",
            details={"quantity": quantity, "unit": unit},
        )
    if component not in _COMPONENT_ALIASES:
        raise FemCoreError(
            "UNSUPPORTED_EXCITATION_COMPONENT",
            "PR5 ELASTIC_SDOF accepts X/UX/U1/1 excitation only",
            details={"component": component},
        )

    times = [_finite(row.get("time_s"), "time_s") for row in rows]
    values = [_finite(row.get("value"), "value") for row in rows]
    steps = [current - previous for previous, current in pairwise(times)]
    if any(step <= 0.0 for step in steps):
        raise FemCoreError("TIME_NOT_STRICTLY_INCREASING", "Canonical load time must be strictly increasing")
    reference = steps[0]
    tolerance = max(abs(reference) * _TIME_RTOL, 1.0e-12)
    if any(abs(step - reference) > tolerance for step in steps[1:]):
        raise FemCoreError("NONUNIFORM_TIME_STEP", "PR5 OpenSees Path loading requires a uniform time step")
    return {
        "timesS": times,
        "values": values,
        "dtS": reference,
        "channelId": channel_id,
        "component": component,
    }


def _opensees_available() -> bool:
    try:
        return importlib.util.find_spec("openseespy.opensees") is not None
    except ModuleNotFoundError:
        return False


def _package_version() -> str | None:
    try:
        return version("openseespy")
    except PackageNotFoundError:
        return None


def _finite(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FemCoreError("INVALID_NUMERIC_VALUE", f"'{field}' must be numeric", details={"field": field}) from exc
    if not math.isfinite(number):
        raise FemCoreError("INVALID_NUMERIC_VALUE", f"'{field}' must be finite", details={"field": field})
    return number


def _positive_finite(value: Any, field: str) -> float:
    number = _finite(value, field)
    if number <= 0.0:
        raise FemCoreError("INVALID_NUMERIC_VALUE", f"'{field}' must be positive", details={"field": field})
    return number


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
