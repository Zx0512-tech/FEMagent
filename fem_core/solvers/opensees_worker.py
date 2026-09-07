from __future__ import annotations

import argparse
import csv
import json
import math
import os
import runpy
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.opensees_response_plan import (
    opensees_response_mapping,
    validate_opensees_response_plan_domain,
)
from fem_core.solvers.opensees import read_canonical_uniform_excitation, read_opensees_model_spec

_VERIFIED_CONTEXT_KEYS = {"schemaVersion", "kind", "channels"}
_VERIFIED_CHANNEL_KEYS = {
    "channelId",
    "quantity",
    "target",
    "component",
    "location",
    "access",
    "dof",
    "response",
    "index",
    "vectorLength",
    "referenceFrame",
    "unit",
}


def _execute_python_entrypoint(model_path: Path) -> tuple[Any, Path, list[str]]:
    import openseespy.opensees as ops

    entrypoint = model_path.resolve()
    project_dir = entrypoint.parent
    original_cwd = Path.cwd()
    original_sys_path = list(sys.path)
    ops.wipe()
    os.chdir(project_dir)
    sys.path.insert(0, str(project_dir))
    return ops, original_cwd, original_sys_path


def _restore_python_entrypoint(ops: Any, original_cwd: Path, original_sys_path: list[str]) -> None:
    sys.path[:] = original_sys_path
    os.chdir(original_cwd)
    ops.wipe()


def _element_types(ops: Any) -> dict[str, str]:
    return {str(int(tag)): str(ops.eleType(int(tag))) for tag in ops.getEleTags()}


def run_build_inspection(model_path: Path) -> dict[str, Any]:
    ops, original_cwd, original_sys_path = _execute_python_entrypoint(model_path)
    original_analyze = ops.analyze
    intercepted_analyze_calls = 0

    def blocked_analyze(*_args: Any, **_kwargs: Any) -> int:
        nonlocal intercepted_analyze_calls
        intercepted_analyze_calls += 1
        return 0

    try:
        ops.analyze = blocked_analyze
        runpy.run_path(str(model_path.resolve()), run_name="__femagent_build_inspection__")
        node_tags = sorted(int(tag) for tag in ops.getNodeTags())
        element_tags = sorted(int(tag) for tag in ops.getEleTags())
        coordinates = {
            str(tag): [float(value) for value in ops.nodeCoord(tag)] for tag in node_tags
        }
        analysis_time = float(ops.getTime())
        engine_version = str(ops.version()) if hasattr(ops, "version") else None
        return {
            "status": "COMPLETED",
            "mode": "BUILD_INSPECT",
            "packageVersion": version("openseespy"),
            "engineVersion": engine_version,
            "analysisAdvanced": False,
            "interceptedAnalyzeCalls": intercepted_analyze_calls,
            "nodeTags": node_tags,
            "elementTags": element_tags,
            "elementTypes": _element_types(ops),
            "nodeCoordinates": coordinates,
            "analysisTime": analysis_time,
        }
    finally:
        ops.analyze = original_analyze
        _restore_python_entrypoint(ops, original_cwd, original_sys_path)


def _read_staged_response_plan(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FemCoreError(
            "INVALID_STRUCTURAL_RESPONSE_PLAN",
            "Staged OpenSees Structural Response Plan is invalid UTF-8 JSON",
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schemaVersion") != "1.0"
        or payload.get("kind") != "structural_response_plan"
        or not isinstance(payload.get("channels"), list)
        or not payload["channels"]
    ):
        raise FemCoreError(
            "INVALID_STRUCTURAL_RESPONSE_PLAN",
            "Staged OpenSees Structural Response Plan is invalid",
        )
    return payload


def _invalid_verified_context(message: str, **details: Any) -> FemCoreError:
    return FemCoreError("INVALID_VERIFIED_RESPONSE_CONTEXT", message, details=details)


def _read_verified_response_context(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _invalid_verified_context(
            "Verified OpenSees response context must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict) or set(payload) != _VERIFIED_CONTEXT_KEYS:
        raise _invalid_verified_context("Verified OpenSees response context has an invalid shape")
    if payload.get("schemaVersion") != "1.0" or payload.get("kind") != (
        "verified_structural_response_context"
    ):
        raise _invalid_verified_context("Verified OpenSees response context identity is invalid")
    raw_channels = payload.get("channels")
    if not isinstance(raw_channels, list) or not raw_channels:
        raise _invalid_verified_context("Verified OpenSees response context requires channels")

    seen_ids: set[str] = set()
    channels: list[dict[str, Any]] = []
    for index, channel in enumerate(raw_channels):
        if not isinstance(channel, dict) or not set(channel).issubset(_VERIFIED_CHANNEL_KEYS):
            raise _invalid_verified_context(
                "Verified OpenSees response channel has an invalid shape",
                channelIndex=index,
            )
        channel_id = channel.get("channelId")
        if not isinstance(channel_id, str) or not channel_id or channel_id in seen_ids:
            raise _invalid_verified_context(
                "Verified OpenSees response channelId is invalid or duplicated",
                channelIndex=index,
            )
        seen_ids.add(channel_id)
        target = channel.get("target")
        if (
            not isinstance(target, dict)
            or target.get("type") not in {"NODE", "ELEMENT"}
            or not isinstance(target.get("id"), int)
            or isinstance(target.get("id"), bool)
            or int(target["id"]) <= 0
        ):
            raise _invalid_verified_context(
                "Verified OpenSees response target is invalid",
                channelId=channel_id,
            )
        unit = channel.get("unit")
        reference_frame = channel.get("referenceFrame")
        if not isinstance(unit, str) or not unit:
            raise _invalid_verified_context(
                "Verified OpenSees response unit is invalid",
                channelId=channel_id,
            )
        if reference_frame not in {"GLOBAL", "ELEMENT_LOCAL"}:
            raise _invalid_verified_context(
                "Verified OpenSees response reference frame is invalid",
                channelId=channel_id,
            )
        access = channel.get("access")
        if access in {"NODE_DISP", "NODE_REACTION"}:
            dof = channel.get("dof")
            if not isinstance(dof, int) or isinstance(dof, bool) or dof <= 0:
                raise _invalid_verified_context(
                    "Verified OpenSees nodal response DOF is invalid",
                    channelId=channel_id,
                )
        elif access == "ELEMENT_LOCAL_FORCE":
            response = channel.get("response")
            response_index = channel.get("index")
            vector_length = channel.get("vectorLength")
            if response != "localForce":
                raise _invalid_verified_context(
                    "Verified OpenSees element response accessor is invalid",
                    channelId=channel_id,
                )
            if (
                not isinstance(response_index, int)
                or isinstance(response_index, bool)
                or not isinstance(vector_length, int)
                or isinstance(vector_length, bool)
                or response_index < 0
                or vector_length <= response_index
            ):
                raise _invalid_verified_context(
                    "Verified OpenSees element response index contract is invalid",
                    channelId=channel_id,
                )
        else:
            raise _invalid_verified_context(
                "Verified OpenSees response access mode is unsupported",
                channelId=channel_id,
                access=access,
            )
        channels.append(dict(channel))
    return {
        "schemaVersion": "1.0",
        "kind": "verified_structural_response_context",
        "channels": channels,
    }


def _response_identity(channel: dict[str, Any]) -> dict[str, Any]:
    identity = {
        "channelId": channel["channelId"],
        "quantity": channel["quantity"],
        "target": dict(channel["target"]),
        "component": channel["component"],
    }
    if "location" in channel:
        identity["location"] = channel["location"]
    return identity


def _write_structural_response(
    run_dir: Path,
    *,
    channels_source: dict[str, Any],
    samples: dict[str, dict[str, list[float]]],
    mappings: dict[str, dict[str, Any]],
) -> Path:
    channels: list[dict[str, Any]] = []
    for channel in channels_source["channels"]:
        channel_id = channel["channelId"]
        sample = samples[channel_id]
        mapping = mappings[channel_id]
        if not sample["values"] or len(sample["values"]) != len(sample["abscissaValues"]):
            raise FemCoreError(
                "RESULT_SERIES_UNAVAILABLE",
                "OpenSees structural response channel produced no complete samples",
                details={"channelId": channel_id},
            )
        channels.append(
            {
                **_response_identity(channel),
                "unit": mapping["unit"],
                "referenceFrame": mapping["referenceFrame"],
                "abscissaSemantic": "SOLVER_NATIVE_RESULT_ABSCISSA",
                "abscissaUnit": None,
                "abscissaValues": sample["abscissaValues"],
                "values": sample["values"],
            }
        )
    path = run_dir / "structural_response.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "kind": "structural_response_series",
                "channels": channels,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _sample_response_channel(
    ops: Any,
    *,
    channel: dict[str, Any],
    mapping: dict[str, Any],
) -> float:
    channel_id = channel["channelId"]
    target_id = int(channel["target"]["id"])
    access = mapping.get("access")
    if access == "NODE_DISP":
        value = float(ops.nodeDisp(target_id, int(mapping["dof"])))
    elif access == "NODE_REACTION":
        value = float(ops.nodeReaction(target_id, int(mapping["dof"])))
    elif access == "ELEMENT_LOCAL_FORCE":
        vector = ops.eleResponse(target_id, mapping["response"])
        if not isinstance(vector, (list, tuple)) or len(vector) != mapping["vectorLength"]:
            raise FemCoreError(
                "STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE",
                "OpenSees element response vector does not match the proven mapping contract",
                details={
                    "channelId": channel_id,
                    "elementId": target_id,
                    "expectedLength": mapping["vectorLength"],
                    "actualLength": len(vector) if hasattr(vector, "__len__") else None,
                },
            )
        value = float(vector[mapping["index"]])
    else:
        raise FemCoreError(
            "STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE",
            "OpenSees worker received an unsupported response access mode",
            details={"channelId": channel_id, "access": access},
        )
    if not math.isfinite(value):
        raise FemCoreError(
            "INVALID_RESULT_SERIES",
            "OpenSees structural response contains a non-finite value",
            details={"channelId": channel_id},
        )
    return value


def run_python_model(
    model_path: Path,
    run_dir: Path,
    response_plan_path: Path | None = None,
    response_context_path: Path | None = None,
) -> dict[str, Any]:
    if response_plan_path is not None and response_context_path is not None:
        raise FemCoreError(
            "INVALID_STRUCTURAL_RESPONSE_CONFIGURATION",
            "OpenSees script run cannot combine a legacy response plan with verified response context",
        )

    ops, original_cwd, original_sys_path = _execute_python_entrypoint(model_path)
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_path = run_dir / "result_summary.json"
    original_analyze = ops.analyze
    plan = _read_staged_response_plan(response_plan_path) if response_plan_path is not None else None
    verified_context = (
        _read_verified_response_context(response_context_path)
        if response_context_path is not None
        else None
    )
    channels_source = verified_context if verified_context is not None else plan
    mappings: dict[str, dict[str, Any]] = {}
    samples: dict[str, dict[str, list[float]]] = {}
    mapping_validated = verified_context is not None

    if verified_context is not None:
        mappings = {
            channel["channelId"]: dict(channel) for channel in verified_context["channels"]
        }
    if channels_source is not None:
        samples = {
            channel["channelId"]: {"abscissaValues": [], "values": []}
            for channel in channels_source["channels"]
        }

    def instrumented_analyze(*args: Any, **kwargs: Any) -> int:
        nonlocal mapping_validated
        if plan is not None and not mapping_validated:
            element_types = _element_types(ops)
            validate_opensees_response_plan_domain(plan, element_types=element_types)
            for channel in plan["channels"]:
                element_id = int(channel["target"]["id"])
                mappings[channel["channelId"]] = {
                    "access": "ELEMENT_LOCAL_FORCE",
                    **opensees_response_mapping(
                        channel,
                        element_type=element_types[str(element_id)],
                    ),
                }
            mapping_validated = True

        code = int(original_analyze(*args, **kwargs))
        if code == 0 and channels_source is not None:
            abscissa = float(ops.getTime())
            if not math.isfinite(abscissa):
                raise FemCoreError("INVALID_RESULT_SERIES", "OpenSees analysis abscissa is non-finite")
            if any(mapping.get("access") == "NODE_REACTION" for mapping in mappings.values()):
                ops.reactions()
            for channel in channels_source["channels"]:
                channel_id = channel["channelId"]
                value = _sample_response_channel(
                    ops,
                    channel=channel,
                    mapping=mappings[channel_id],
                )
                samples[channel_id]["abscissaValues"].append(abscissa)
                samples[channel_id]["values"].append(value)
        return code

    try:
        if channels_source is not None:
            ops.analyze = instrumented_analyze
        runpy.run_path(str(model_path.resolve()), run_name="__femagent_solver_run__")
        node_tags = sorted(int(tag) for tag in ops.getNodeTags())
        element_tags = sorted(int(tag) for tag in ops.getEleTags())
        analysis_time = float(ops.getTime())
        structural_response = None
        if channels_source is not None:
            if not mapping_validated:
                raise FemCoreError(
                    "RESULT_SERIES_UNAVAILABLE",
                    "OpenSees model did not execute an analysis for the requested structural response",
                )
            structural_response = _write_structural_response(
                run_dir,
                channels_source=channels_source,
                samples=samples,
                mappings=mappings,
            )
        summary = {
            "nodeCount": len(node_tags),
            "elementCount": len(element_tags),
            "nodeTags": node_tags,
            "elementTags": element_tags,
            "analysisTime": analysis_time,
        }
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        engine_version = str(ops.version()) if hasattr(ops, "version") else None
        return {
            "status": "COMPLETED",
            "packageVersion": version("openseespy"),
            "engineVersion": engine_version,
            "analysis": {
                "type": "MODEL_SCRIPT",
                "analysisTime": analysis_time,
            },
            "summary": summary,
            "structuralResponse": str(structural_response) if structural_response is not None else None,
        }
    finally:
        ops.analyze = original_analyze
        _restore_python_entrypoint(ops, original_cwd, original_sys_path)


def run_worker(model_path: Path, load_path: Path, run_dir: Path) -> dict[str, Any]:
    import openseespy.opensees as ops

    model = read_opensees_model_spec(model_path)
    load = read_canonical_uniform_excitation(load_path)
    run_dir.mkdir(parents=True, exist_ok=True)
    response_path = run_dir / "response.csv"
    summary_path = run_dir / "result_summary.json"

    mass = model["massKg"]
    stiffness = model["stiffnessNPerM"]
    damping_ratio = model["dampingRatio"]
    omega = math.sqrt(stiffness / mass)
    alpha_m = 2.0 * damping_ratio * omega
    dt = load["dtS"]
    times = load["timesS"]
    values = load["values"]

    responses: list[tuple[float, float, float, float]] = [(times[0], 0.0, 0.0, 0.0)]
    ops.wipe()
    try:
        ops.model("basic", "-ndm", 1, "-ndf", 1)
        ops.node(1, 0.0)
        ops.node(2, 0.0)
        ops.fix(1, 1)
        ops.mass(2, mass)
        ops.uniaxialMaterial("Elastic", 1, stiffness)
        ops.element("zeroLength", 1, 1, 2, "-mat", 1, "-dir", 1)
        ops.rayleigh(alpha_m, 0.0, 0.0, 0.0)

        ops.timeSeries("Path", 1, "-dt", dt, "-values", *values)
        ops.pattern("UniformExcitation", 1, 1, "-accel", 1)
        ops.constraints("Plain")
        ops.numberer("Plain")
        ops.system("BandGeneral")
        ops.test("NormDispIncr", 1.0e-12, 20, 0)
        ops.algorithm("Newton")
        ops.integrator("Newmark", 0.5, 0.25)
        ops.analysis("Transient")

        for index in range(1, len(times)):
            code = int(ops.analyze(1, dt))
            if code != 0:
                raise RuntimeError(f"OpenSees analyze failed at step {index} with code {code}")
            responses.append(
                (
                    times[index],
                    float(ops.nodeDisp(2, 1)),
                    float(ops.nodeVel(2, 1)),
                    float(ops.nodeAccel(2, 1)),
                )
            )
    finally:
        ops.wipe()

    with response_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            [
                "time_s",
                "relative_displacement_m",
                "relative_velocity_m_s",
                "relative_acceleration_m_s2",
            ]
        )
        for row in responses:
            writer.writerow([format(value, ".15g") for value in row])

    peak_index = max(range(len(responses)), key=lambda index: abs(responses[index][1]))
    displacements = [row[1] for row in responses]
    summary = {
        "responseNode": 2,
        "responseDof": 1,
        "sampleCount": len(responses),
        "minDisplacementM": min(displacements),
        "maxDisplacementM": max(displacements),
        "absolutePeakDisplacementM": abs(responses[peak_index][1]),
        "timeAtAbsolutePeakS": responses[peak_index][0],
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    engine_version = str(ops.version()) if hasattr(ops, "version") else None
    return {
        "status": "COMPLETED",
        "packageVersion": version("openseespy"),
        "engineVersion": engine_version,
        "analysis": {
            "type": "TRANSIENT_UNIFORM_EXCITATION",
            "integrator": "Newmark(0.5,0.25)",
            "algorithm": "Newton",
            "system": "BandGeneral",
            "dtS": dt,
            "analysisSteps": len(times) - 1,
            "sourceTimeStartS": times[0],
            "sourceTimeEndS": times[-1],
        },
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("run", "build-inspect", "script-run"), default="run")
    parser.add_argument("--model", required=True)
    parser.add_argument("--load")
    parser.add_argument("--run-dir")
    parser.add_argument("--response-plan")
    parser.add_argument("--response-context")
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    result_path = Path(args.result).resolve()
    try:
        if args.mode == "build-inspect":
            result = run_build_inspection(Path(args.model).resolve())
        elif args.mode == "script-run":
            if not args.run_dir:
                raise ValueError("script-run mode requires --run-dir")
            result = run_python_model(
                Path(args.model).resolve(),
                Path(args.run_dir).resolve(),
                Path(args.response_plan).resolve() if args.response_plan else None,
                Path(args.response_context).resolve() if args.response_context else None,
            )
        else:
            if not args.load or not args.run_dir:
                raise ValueError("run mode requires --load and --run-dir")
            result = run_worker(
                Path(args.model).resolve(),
                Path(args.load).resolve(),
                Path(args.run_dir).resolve(),
            )
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return 0
    except Exception as exc:  # noqa: BLE001 - isolated native-solver boundary must fail closed.
        code = exc.code if isinstance(exc, FemCoreError) else type(exc).__name__
        result_path.write_text(
            json.dumps(
                {"status": "FAILED", "error": type(exc).__name__, "code": code, "message": str(exc)},
                indent=2,
            ),
            encoding="utf-8",
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
