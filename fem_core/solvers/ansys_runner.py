from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from fem_core.ansys_bundle import ANSYS_BUNDLE_SUFFIXES
from fem_core.errors import FemCoreError
from fem_core.text import decode_engineering_text

ANSYS_PROCESS_TIMEOUT_S = 120.0


def sanitize_apdl_for_build(text: str) -> str:
    """Keep preprocessing commands while preventing a requested solution/postprocess stage."""

    output: list[str] = []
    for line in text.splitlines():
        command = line.split("!", 1)[0].strip().upper()
        if command.startswith(("/SOLU", "/POST")) or command == "SOLU":
            output.append(f"! FEMagent build-only stopped before: {line.strip()}")
            break
        if command.startswith(("SOLVE", "LSSOLVE", "MSSOLVE", "PSOLVE")):
            output.append(f"! FEMagent build-only suppressed: {line.strip()}")
            continue
        output.append(line)
    output.extend(["FINISH", "/EXIT,NOSAVE"])
    return "\n".join(output) + "\n"


def stage_ansys_bundle(
    workspace: Path,
    bundle: dict[str, Any],
    stage_root: Path,
    *,
    sanitize_for_build: bool,
) -> dict[str, Path]:
    root = workspace.resolve()
    stage = stage_root.resolve()
    stage.mkdir(parents=True, exist_ok=False)

    for file_info in bundle["files"]:
        relative = Path(str(file_info["path"]))
        source = (root / relative).resolve()
        destination = (stage / relative).resolve()
        try:
            destination.relative_to(stage)
        except ValueError as exc:
            raise FemCoreError(
                "INVALID_MODEL_BUNDLE_PATH",
                "ANSYS Model Bundle stage path escaped the staging root",
                details={"path": str(relative)},
            ) from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        if sanitize_for_build and source.suffix.lower() in ANSYS_BUNDLE_SUFFIXES:
            content = source.read_bytes()
            text, _ = decode_engineering_text(content)
            destination.write_text(sanitize_apdl_for_build(text), encoding="utf-8")
        else:
            shutil.copy2(source, destination)

    entrypoint = (stage / str(bundle["entrypoint"]["path"])).resolve()
    working_directory = (stage / str(bundle.get("workingDirectory") or ".")).resolve()
    working_directory.mkdir(parents=True, exist_ok=True)
    return {
        "stageRoot": stage,
        "entrypoint": entrypoint,
        "workingDirectory": working_directory,
    }


def write_build_only_wrapper(staged: dict[str, Path]) -> Path:
    entrypoint = staged["entrypoint"]
    working_directory = staged["workingDirectory"]
    try:
        relative_entrypoint = entrypoint.relative_to(working_directory)
    except ValueError as exc:
        raise FemCoreError(
            "INVALID_MODEL_BUNDLE_PATH",
            "ANSYS entrypoint is outside its staged working directory",
        ) from exc
    if len(relative_entrypoint.parts) != 1:
        raise FemCoreError(
            "INVALID_MODEL_BUNDLE_PATH",
            "ANSYS PR8 requires the entrypoint to reside in the bundle working directory",
            details={"entrypoint": str(relative_entrypoint)},
        )

    suffix = entrypoint.suffix.lstrip(".")
    stem = entrypoint.stem
    wrapper = working_directory / "build_only.inp"
    wrapper.write_text(
        f"/INPUT,'{stem}','{suffix}'\nFINISH\n/EXIT,NOSAVE\n",
        encoding="utf-8",
    )
    return wrapper


def run_ansys_process(
    executable: Path,
    *,
    input_path: Path,
    output_path: Path,
    cwd: Path,
    jobname: str,
    timeout_s: float = ANSYS_PROCESS_TIMEOUT_S,
) -> dict[str, Any]:
    command = [
        str(executable),
        "-b",
        "-i",
        str(input_path),
        "-o",
        str(output_path),
        "-j",
        jobname,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FemCoreError(
            "SOLVER_TIMEOUT",
            "ANSYS process exceeded the configured execution timeout",
            details={"timeoutS": timeout_s},
        ) from exc
    except OSError as exc:
        raise FemCoreError(
            "SOLVER_START_FAILED",
            "ANSYS configured runtime could not be started",
            details={"executable": str(executable), "reason": str(exc)},
        ) from exc

    return {
        "command": command,
        "returnCode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
