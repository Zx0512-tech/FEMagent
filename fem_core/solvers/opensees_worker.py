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

from fem_core.solvers.opensees import read_canonical_uniform_excitation, read_opensees_model_spec


def run_build_inspection(model_path: Path) -> dict[str, Any]:
    import openseespy.opensees as ops

    entrypoint = model_path.resolve()
    project_dir = entrypoint.parent
    original_cwd = Path.cwd()
    original_sys_path = list(sys.path)
    original_analyze = ops.analyze
    intercepted_analyze_calls = 0

    def blocked_analyze(*_args: Any, **_kwargs: Any) -> int:
        nonlocal intercepted_analyze_calls
        intercepted_analyze_calls += 1
        return 0

    ops.wipe()
    try:
        ops.analyze = blocked_analyze
        os.chdir(project_dir)
        sys.path.insert(0, str(project_dir))
        runpy.run_path(str(entrypoint), run_name="__femagent_build_inspection__")
        node_tags = sorted(int(tag) for tag in ops.getNodeTags())
        element_tags = sorted(int(tag) for tag in ops.getEleTags())
        coordinates = {
            str(tag): [float(value) for value in ops.nodeCoord(tag)]
            for tag in node_tags
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
            "nodeCoordinates": coordinates,
            "analysisTime": analysis_time,
        }
    finally:
        ops.analyze = original_analyze
        sys.path[:] = original_sys_path
        os.chdir(original_cwd)
        ops.wipe()


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
        writer.writerow(["time_s", "relative_displacement_m", "relative_velocity_m_s", "relative_acceleration_m_s2"])
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
    parser.add_argument("--mode", choices=("run", "build-inspect"), default="run")
    parser.add_argument("--model", required=True)
    parser.add_argument("--load")
    parser.add_argument("--run-dir")
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    result_path = Path(args.result).resolve()
    try:
        if args.mode == "build-inspect":
            result = run_build_inspection(Path(args.model).resolve())
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
        result_path.write_text(
            json.dumps({"status": "FAILED", "error": type(exc).__name__, "message": str(exc)}, indent=2),
            encoding="utf-8",
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
