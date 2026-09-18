from __future__ import annotations

import json
import math
from hashlib import sha256
from pathlib import Path
from typing import Any

from fem_core.analysis_spec.transient_artifact import (
    acceleration_m_s2_to_model_factor,
    read_transient_load_artifact,
    seconds_to_model_time_factor,
)
from fem_core.analysis_spec.validator import validate_engineering_analysis_spec
from fem_core.ansys_bundle import ANSYS_BUNDLE_SUFFIXES
from fem_core.errors import FemCoreError
from fem_core.model_inspection import inspect_model
from fem_core.pathing import resolve_workspace_file
from fem_core.solvers.ansys_load import (
    inspect_ansys_transient_injection,
    read_ansys_canonical_uniform_excitation,
)
from fem_core.text import decode_engineering_text

ANSYS_V2_PROFILE = "ANSYS_APDL_TRANSIENT_UNIFORM_BASE_V2"
ANSYS_V2_ADMISSION_SCHEMA = "FEMAGENT_ANSYS_V2_EXECUTION_ADMISSION_V1"
_CONTROL_MACRO_NAME = "femagent_analysis_v2"
_SOLVE_COMMANDS = frozenset({"SOLVE", "LSSOLVE", "MSSOLVE", "PSOLVE"})
_DAMPING_COMMANDS = frozenset({"ALPHAD", "BETAD", "DMPR", "DMPRAT", "DMPSTR", "MDAMP"})
_SUPPORTED_RESULT_QUANTITIES = frozenset({"DISPLACEMENT", "REACTION_FORCE"})
_COMPONENT_TO_DOF = {"X": "UX", "Y": "UY"}
_TIME_ABS_TOL = 1e-12


def _active_command(line: str) -> str:
    return line.split("!", 1)[0].strip()


def _fields(command: str) -> list[str]:
    return [field.strip() for field in command.split(",")]


def _upper_fields(command: str) -> list[str]:
    return [field.upper() for field in _fields(command)]


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _format_apdl_number(value: float) -> str:
    return format(float(value), ".15g")


def _supported_model_units(model_units: dict[str, Any]) -> dict[str, str]:
    if not isinstance(model_units, dict):
        raise FemCoreError(
            "ANSYS_MODEL_UNITS_REQUIRED",
            "ANSYS V2 execution requires explicit modelUnits.length and modelUnits.time",
        )
    length = model_units.get("length")
    time = model_units.get("time")
    if length not in {"m", "cm", "mm"} or time not in {"s", "ms"}:
        raise FemCoreError(
            "UNSUPPORTED_ANSYS_MODEL_UNITS",
            "ANSYS V2 execution supports length m/cm/mm and time s/ms",
            details={"length": length, "time": time},
        )
    return {"length": str(length), "time": str(time)}


def _bundle_source_records(
    workspace: Path,
    bundle: dict[str, Any],
) -> list[tuple[str, list[str]]]:
    root = workspace.resolve()
    records: list[tuple[str, list[str]]] = []
    for file_info in bundle.get("files", []):
        relative = Path(str(file_info.get("path") or ""))
        if relative.suffix.lower() not in ANSYS_BUNDLE_SUFFIXES:
            continue
        source = (root / relative).resolve()
        try:
            source.relative_to(root)
        except ValueError as exc:
            raise FemCoreError(
                "PATH_OUTSIDE_WORKSPACE",
                "ANSYS V2 admission may only inspect workspace-local bundle files",
                details={"path": relative.as_posix()},
            ) from exc
        text, _ = decode_engineering_text(source.read_bytes())
        records.append((relative.as_posix(), text.splitlines()))
    return records


def _static_control_evidence(
    workspace: Path,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    constraints: dict[int, set[str]] = {}
    solve_hooks: list[dict[str, Any]] = []
    damping_conflicts: list[dict[str, Any]] = []

    for source_path, lines in _bundle_source_records(workspace, bundle):
        for line_number, raw_line in enumerate(lines, start=1):
            command = _active_command(raw_line)
            if not command:
                continue
            fields = _upper_fields(command)
            keyword = fields[0]

            if keyword == "D" and len(fields) >= 3:
                try:
                    node_id = int(fields[1])
                except ValueError:
                    continue
                labels = {
                    item
                    for item in fields[2:]
                    if item in {"ALL", "UX", "UY", "UZ", "ROTX", "ROTY", "ROTZ"}
                }
                if labels:
                    constraints.setdefault(node_id, set()).update(labels)

            if keyword in _SOLVE_COMMANDS:
                solve_hooks.append(
                    {
                        "path": source_path,
                        "line": line_number,
                        "command": command,
                    }
                )

            if keyword in _DAMPING_COMMANDS:
                damping_conflicts.append(
                    {
                        "path": source_path,
                        "line": line_number,
                        "command": command,
                    }
                )
            elif keyword == "MP" and len(fields) >= 2 and fields[1] in {"ALPD", "BETD", "DMPR"}:
                damping_conflicts.append(
                    {
                        "path": source_path,
                        "line": line_number,
                        "command": command,
                    }
                )

    if len(solve_hooks) != 1:
        raise FemCoreError(
            "ANSYS_V2_SOLVE_HOOK_AMBIGUOUS",
            "ANSYS V2 execution requires exactly one explicit solve command",
            details={"solveHooks": solve_hooks},
        )
    if damping_conflicts:
        raise FemCoreError(
            "ANSYS_V2_DAMPING_CONFLICT",
            "ANSYS V2 execution requires the source bundle to omit active damping commands",
            details={"conflicts": damping_conflicts},
        )
    return {
        "constraints": constraints,
        "solveHook": solve_hooks[0],
    }


def _validate_profile(normalized_analysis: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if normalized_analysis.get("schemaVersion") != "2.0":
        raise FemCoreError(
            "ANSYS_V2_PROFILE_UNSUPPORTED",
            "ANSYS PR29 accepts EngineeringAnalysisSpec V2 only",
        )
    if normalized_analysis.get("analysisType") != "TRANSIENT":
        raise FemCoreError(
            "ANSYS_V2_PROFILE_UNSUPPORTED",
            "ANSYS PR29 accepts TRANSIENT analysis only",
        )
    definition = normalized_analysis.get("definition")
    if not isinstance(definition, dict):
        raise FemCoreError("ANSYS_V2_PROFILE_UNSUPPORTED", "Transient definition is required")
    excitation = definition.get("excitation")
    time_definition = definition.get("time")
    if not isinstance(excitation, dict) or not isinstance(time_definition, dict):
        raise FemCoreError(
            "ANSYS_V2_PROFILE_UNSUPPORTED",
            "Transient time and excitation definitions are required",
        )
    if (
        excitation.get("type") != "UNIFORM_BASE_EXCITATION"
        or excitation.get("quantity") != "ACCELERATION"
        or excitation.get("component") not in {"X", "Y"}
    ):
        raise FemCoreError(
            "ANSYS_V2_PROFILE_UNSUPPORTED",
            "ANSYS PR29 supports X/Y UNIFORM_BASE_EXCITATION acceleration only",
            details={
                "type": excitation.get("type"),
                "quantity": excitation.get("quantity"),
                "component": excitation.get("component"),
            },
        )
    return definition, excitation


def _validate_result_requests(
    requests: list[dict[str, Any]],
    *,
    node_tags: set[int],
    constraints: dict[int, set[str]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for request in requests:
        quantity = str(request.get("quantity") or "")
        target = request.get("target")
        component = str(request.get("component") or "")
        request_id = str(request.get("requestId") or "")
        if (
            quantity not in _SUPPORTED_RESULT_QUANTITIES
            or not isinstance(target, dict)
            or target.get("type") != "NODE"
            or component not in _COMPONENT_TO_DOF
        ):
            raise FemCoreError(
                "ANSYS_V2_RESULT_MAPPING_UNSUPPORTED",
                "ANSYS PR29 supports NODE DISPLACEMENT/REACTION_FORCE X/Y requests only",
                details={"requestId": request_id, "quantity": quantity},
            )
        node_id = target.get("id")
        if not isinstance(node_id, int) or isinstance(node_id, bool) or node_id not in node_tags:
            raise FemCoreError(
                "ANSYS_V2_RESULT_NODE_NOT_FOUND",
                "ANSYS V2 result request node is not statically proven in the APDL bundle",
                details={"requestId": request_id, "nodeId": node_id},
            )
        if quantity == "REACTION_FORCE":
            dof = _COMPONENT_TO_DOF[component]
            labels = constraints.get(node_id, set())
            if "ALL" not in labels and dof not in labels:
                raise FemCoreError(
                    "ANSYS_V2_REACTION_DOF_UNRESTRAINED",
                    "ANSYS V2 reaction request requires a statically explicit restrained DOF",
                    details={"requestId": request_id, "nodeId": node_id, "dof": dof},
                )
        normalized.append(dict(request))
    normalized.sort(key=lambda item: str(item["requestId"]))
    return normalized


def _validate_load_and_time(
    workspace: Path,
    *,
    excitation: dict[str, Any],
    time_definition: dict[str, Any],
    model_units: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    evidence = read_transient_load_artifact(workspace, excitation["loadArtifact"])
    expected = {
        "loadKind": "EARTHQUAKE",
        "applicationType": "UNIFORM_EXCITATION",
        "targetType": "",
        "targetId": "",
        "component": str(excitation["component"]),
        "quantity": "ACCELERATION",
        "unit": "m/s2",
    }
    received = {key: str(evidence.get(key, "")) for key in expected}
    if received != expected:
        raise FemCoreError(
            "ANSYS_V2_LOAD_CHANNEL_MISMATCH",
            "Canonical load channel does not match the ANSYS V2 uniform-base AnalysisSpec",
            details={"expected": expected, "received": received},
        )

    model_units_per_second = seconds_to_model_time_factor(model_units["time"])
    expected_dt_s = float(time_definition["timeStep"]) / model_units_per_second
    expected_duration_s = float(time_definition["duration"]) / model_units_per_second
    if not math.isclose(float(evidence["timeStartS"]), 0.0, rel_tol=0.0, abs_tol=_TIME_ABS_TOL):
        raise FemCoreError(
            "ANSYS_V2_TIME_ORIGIN_MISMATCH",
            "ANSYS V2 earthquake artifact must start at canonical time zero",
        )
    if not math.isclose(
        float(evidence["dtS"]),
        expected_dt_s,
        rel_tol=1e-9,
        abs_tol=_TIME_ABS_TOL,
    ):
        raise FemCoreError(
            "ANSYS_V2_TIME_STEP_MISMATCH",
            "ANSYS V2 earthquake artifact interval does not match AnalysisSpec timeStep",
            details={"expectedTimeStepS": expected_dt_s, "artifactTimeStepS": evidence["dtS"]},
        )
    if not math.isclose(
        float(evidence["timeEndS"]),
        expected_duration_s,
        rel_tol=1e-9,
        abs_tol=_TIME_ABS_TOL,
    ):
        raise FemCoreError(
            "ANSYS_V2_DURATION_MISMATCH",
            "ANSYS V2 earthquake artifact final time does not match AnalysisSpec duration",
            details={
                "expectedDurationS": expected_duration_s,
                "artifactTimeEndS": evidence["timeEndS"],
            },
        )

    ratio = float(time_definition["duration"]) / float(time_definition["timeStep"])
    analysis_steps = round(ratio)
    if analysis_steps <= 0 or not math.isclose(
        ratio,
        analysis_steps,
        rel_tol=1e-9,
        abs_tol=1e-12,
    ):
        raise FemCoreError(
            "ANSYS_V2_DURATION_MISMATCH",
            "ANSYS V2 duration must contain an integer number of fixed analysis steps",
        )

    load_file = resolve_workspace_file(workspace, str(evidence["path"]))
    canonical_load = read_ansys_canonical_uniform_excitation(load_file, model_units)
    if canonical_load["sha256"] != evidence["sha256"]:
        raise FemCoreError(
            "TRANSIENT_ARTIFACT_HASH_MISMATCH",
            "ANSYS canonical load reader disagrees with verified transient artifact identity",
        )

    acceleration_factor, acceleration_unit = acceleration_m_s2_to_model_factor(
        model_units["length"],
        model_units["time"],
    )
    time_report = {
        "timeStepModel": float(time_definition["timeStep"]),
        "durationModel": float(time_definition["duration"]),
        "analysisSteps": analysis_steps,
        "timeUnit": model_units["time"],
    }
    load_report = {
        "path": str(evidence["path"]),
        "sha256": str(evidence["sha256"]),
        "format": str(evidence["format"]),
        "loadKind": "EARTHQUAKE",
        "applicationType": "UNIFORM_EXCITATION",
        "component": str(excitation["component"]),
        "quantity": "ACCELERATION",
        "canonicalUnit": "m/s2",
        "modelUnit": acceleration_unit,
        "accelerationFactorFromMPerS2": acceleration_factor,
        "sampleCount": int(evidence["sampleCount"]),
    }
    return time_report, load_report, canonical_load


def _damping_report(definition: dict[str, Any]) -> dict[str, Any]:
    damping = definition.get("damping")
    if not isinstance(damping, dict):
        raise FemCoreError("ANSYS_V2_PROFILE_UNSUPPORTED", "Explicit damping definition is required")
    if damping.get("type") == "NONE":
        return {"type": "NONE"}
    if damping.get("type") == "RAYLEIGH":
        return {
            "type": "RAYLEIGH",
            "alphaM": float(damping["alphaM"]),
            "betaK": float(damping["betaK"]),
        }
    raise FemCoreError(
        "ANSYS_V2_PROFILE_UNSUPPORTED",
        "ANSYS PR29 supports explicit NONE or RAYLEIGH damping only",
    )


def _intent_fingerprint(plan: dict[str, Any]) -> str:
    payload = {
        "profile": plan["profile"],
        "analysisSpecFingerprint": plan["analysisSpecFingerprint"],
        "currentBundleFingerprint": plan["binding"]["currentBundleFingerprint"],
        "loadSha256": plan["load"]["sha256"],
        "modelUnits": plan["modelUnits"],
        "time": plan["time"],
        "damping": plan["damping"],
        "resultRequests": plan["resultRequests"],
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_ansys_v2_execution_plan(
    workspace: Path,
    *,
    model_path: str,
    analysis_spec: dict[str, Any],
    model_units: dict[str, Any],
    confirmed_bundle_fingerprint: str,
) -> dict[str, Any]:
    units = _supported_model_units(model_units)
    validation = validate_engineering_analysis_spec(analysis_spec)
    if validation.get("status") != "VALID":
        raise FemCoreError(
            "ANSYS_V2_INVALID_ANALYSIS_SPEC",
            "ANSYS V2 execution requires an intrinsically valid EngineeringAnalysisSpec V2",
            details={"issues": validation.get("issues")},
        )
    normalized_analysis = validation.get("normalizedSpec")
    analysis_fingerprint = validation.get("analysisSpecFingerprint")
    if not isinstance(normalized_analysis, dict) or not isinstance(analysis_fingerprint, str):
        raise FemCoreError(
            "ANSYS_V2_INTERNAL_INVARIANT",
            "Valid AnalysisSpec did not provide normalized identity",
        )
    definition, excitation = _validate_profile(normalized_analysis)

    inspection = inspect_model(workspace, model_path)
    if inspection.get("format") != "ANSYS_APDL_TEXT":
        raise FemCoreError(
            "SOLVER_MODEL_MISMATCH",
            "ANSYS V2 execution requires an ANSYS APDL Model Bundle",
        )
    bundle = inspection.get("bundle")
    if not isinstance(bundle, dict) or bundle.get("integrity") != "VALID":
        raise FemCoreError(
            "MODEL_BUNDLE_BLOCKED",
            "ANSYS V2 execution requires a valid APDL Model Bundle",
        )
    current_bundle_fingerprint = bundle.get("bundleFingerprint")
    if (
        not isinstance(confirmed_bundle_fingerprint, str)
        or len(confirmed_bundle_fingerprint) != 64
        or confirmed_bundle_fingerprint != current_bundle_fingerprint
    ):
        raise FemCoreError(
            "ANSYS_V2_BUNDLE_CONFIRMATION_MISMATCH",
            "Confirmed ANSYS bundle fingerprint does not match the current model bundle",
            details={
                "confirmed": confirmed_bundle_fingerprint,
                "current": current_bundle_fingerprint,
            },
        )

    generation = inspection.get("manifest", {}).get("generation", {})
    node_tags = inspection.get("manifest", {}).get("topology", {}).get("nodeTags")
    if (
        generation.get("parametric")
        or generation.get("blockBased")
        or generation.get("includeDriven")
        or not isinstance(node_tags, list)
    ):
        raise FemCoreError(
            "ANSYS_V2_TOPOLOGY_UNPROVEN",
            "ANSYS PR29 requires a statically enumerable explicit APDL topology",
        )
    proven_node_tags = {
        int(value)
        for value in node_tags
        if isinstance(value, int) and not isinstance(value, bool)
    }

    load_hook = inspect_ansys_transient_injection(workspace, bundle)
    control_evidence = _static_control_evidence(workspace, bundle)
    result_requests = _validate_result_requests(
        normalized_analysis["resultRequests"],
        node_tags=proven_node_tags,
        constraints=control_evidence["constraints"],
    )
    time_report, load_report, canonical_load = _validate_load_and_time(
        workspace,
        excitation=excitation,
        time_definition=definition["time"],
        model_units=units,
    )
    damping = _damping_report(definition)

    plan: dict[str, Any] = {
        "schema": ANSYS_V2_ADMISSION_SCHEMA,
        "status": "ADMITTED",
        "profile": ANSYS_V2_PROFILE,
        "analysisSpecFingerprint": analysis_fingerprint,
        "declaredModelSpecFingerprint": normalized_analysis["modelSpecFingerprint"],
        "binding": {
            "mode": "EXPLICIT_BUNDLE_CONFIRMATION",
            "confirmedBundleFingerprint": confirmed_bundle_fingerprint,
            "currentBundleFingerprint": current_bundle_fingerprint,
            "targetIdPolicy": "IDENTITY",
            "semanticEquivalence": "NOT_MACHINE_PROVEN",
        },
        "modelUnits": units,
        "load": load_report,
        "time": time_report,
        "damping": damping,
        "resultRequests": result_requests,
        "loadHook": load_hook,
        "solveHook": control_evidence["solveHook"],
        "canonicalLoad": canonical_load,
    }
    plan["executionIntentFingerprint"] = _intent_fingerprint(plan)
    return plan


def write_ansys_v2_control_macro(
    working_directory: Path,
    plan: dict[str, Any],
) -> dict[str, Any]:
    working_directory.mkdir(parents=True, exist_ok=True)
    path = working_directory / f"{_CONTROL_MACRO_NAME}.mac"
    time_info = plan["time"]
    damping = plan["damping"]
    lines = [
        "! FEMagent PR29 generated ANSYS V2 transient controls",
        "TRNOPT,FULL",
        "AUTOTS,OFF",
        f"DELTIM,{_format_apdl_number(time_info['timeStepModel'])}",
    ]
    if damping["type"] == "NONE":
        lines.extend(["ALPHAD,0", "BETAD,0"])
    else:
        lines.extend(
            [
                f"ALPHAD,{_format_apdl_number(damping['alphaM'])}",
                f"BETAD,{_format_apdl_number(damping['betaK'])}",
            ]
        )
    lines.extend(
        [
            "OUTRES,NSOL,ALL",
            "OUTRES,RSOL,ALL",
            f"TIME,{_format_apdl_number(time_info['durationModel'])}",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "macroPath": str(path),
        "macroSha256": _sha256_file(path),
        "includeCommand": f"/INPUT,'{_CONTROL_MACRO_NAME}','mac'",
    }


def inject_ansys_v2_controls(
    stage_root: Path,
    solve_hook: dict[str, Any],
) -> dict[str, Any]:
    root = stage_root.resolve()
    target = (root / str(solve_hook["path"])).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise FemCoreError(
            "INVALID_MODEL_BUNDLE_PATH",
            "ANSYS V2 solve hook escaped the staged bundle root",
        ) from exc
    if not target.is_file():
        raise FemCoreError(
            "ANSYS_V2_SOLVE_HOOK_CHANGED",
            "ANSYS V2 staged solve-hook file does not exist",
        )
    text, _ = decode_engineering_text(target.read_bytes())
    lines = text.splitlines()
    line_index = int(solve_hook["line"]) - 1
    if line_index < 0 or line_index >= len(lines):
        raise FemCoreError(
            "ANSYS_V2_SOLVE_HOOK_CHANGED",
            "ANSYS V2 staged solve hook is no longer present",
        )
    expected = _upper_fields(str(solve_hook["command"]))
    received = _upper_fields(_active_command(lines[line_index]))
    if expected != received:
        raise FemCoreError(
            "ANSYS_V2_SOLVE_HOOK_CHANGED",
            "ANSYS V2 staged solve hook no longer matches inspected source",
            details={"expected": solve_hook["command"], "received": lines[line_index]},
        )

    include_command = f"/INPUT,'{_CONTROL_MACRO_NAME}','mac'"
    lines.insert(line_index, include_command)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "injected": True,
        "hook": dict(solve_hook),
        "includeCommand": include_command,
        "stagedHookFile": str(target),
        "stagedHookFileSha256": _sha256_file(target),
    }


def public_ansys_v2_admission(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in plan.items()
        if key not in {"canonicalLoad", "loadHook", "solveHook"}
    }


__all__ = [
    "ANSYS_V2_ADMISSION_SCHEMA",
    "ANSYS_V2_PROFILE",
    "build_ansys_v2_execution_plan",
    "inject_ansys_v2_controls",
    "public_ansys_v2_admission",
    "write_ansys_v2_control_macro",
]
