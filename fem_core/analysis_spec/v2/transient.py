from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from fem_core.analysis_spec.common import (
    SHA256_RE,
    is_finite_number,
    issue,
    validate_exact_keys,
    validate_id_token,
    validate_positive_target_id,
)

_ALLOWED_FORCE_UNITS = {"N", "kN"}
_NODE_XY_QUANTITIES = {"DISPLACEMENT", "VELOCITY", "REACTION_FORCE"}
_BASE_ACCELERATION_QUANTITIES = {"RELATIVE_ACCELERATION", "ABSOLUTE_ACCELERATION"}
_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")


def _validate_time(value: Any, issues: list[dict[str, str]]) -> None:
    if not validate_exact_keys(value, {"timeStep", "duration"}, "definition.time", issues):
        return
    for field in ("timeStep", "duration"):
        number = value.get(field)
        if not is_finite_number(number) or number <= 0:
            issues.append(
                issue(
                    "ANALYSIS_SPEC_INVALID_TIME",
                    f"definition.time.{field}",
                    f"definition.time.{field} must be a positive finite number",
                )
            )


def _validate_damping(value: Any, issues: list[dict[str, str]]) -> None:
    if not isinstance(value, dict):
        validate_exact_keys(value, {"type"}, "definition.damping", issues)
        return

    damping_type = value.get("type")
    if damping_type == "NONE":
        validate_exact_keys(value, {"type"}, "definition.damping", issues)
        return
    if damping_type == "RAYLEIGH":
        validate_exact_keys(
            value,
            {"type", "alphaM", "betaK"},
            "definition.damping",
            issues,
        )
        for field in ("alphaM", "betaK"):
            coefficient = value.get(field)
            if not is_finite_number(coefficient) or coefficient < 0:
                issues.append(
                    issue(
                        "ANALYSIS_SPEC_INVALID_DAMPING_COEFFICIENT",
                        f"definition.damping.{field}",
                        f"definition.damping.{field} must be a non-negative finite number",
                    )
                )
        return

    validate_exact_keys(value, {"type"}, "definition.damping", issues)
    issues.append(
        issue(
            "ANALYSIS_SPEC_UNSUPPORTED_DAMPING",
            "definition.damping.type",
            f"Unsupported transient damping type: {damping_type!r}",
        )
    )


def _validate_artifact(value: Any, *, path: str, issues: list[dict[str, str]]) -> None:
    if not validate_exact_keys(value, {"path", "sha256"}, path, issues):
        return

    locator = value.get("path")
    locator_valid = isinstance(locator, str) and bool(locator.strip())
    if locator_valid:
        syntax_path = locator.replace("\\", "/")
        parsed = PurePosixPath(syntax_path)
        locator_valid = (
            not parsed.is_absolute()
            and _DRIVE_PREFIX_RE.match(syntax_path) is None
            and ".." not in parsed.parts
        )
    if not locator_valid:
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_ARTIFACT_PATH",
                f"{path}.path",
                f"{path}.path must be a non-empty workspace-relative locator without parent traversal",
            )
        )

    sha256 = value.get("sha256")
    if not isinstance(sha256, str) or SHA256_RE.fullmatch(sha256) is None:
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_ARTIFACT_SHA",
                f"{path}.sha256",
                f"{path}.sha256 must be lowercase SHA-256 hex",
            )
        )


def _validate_units(spec: dict[str, Any], excitation_type: str | None, issues: list[dict[str, str]]) -> None:
    units = spec.get("units")
    if excitation_type == "NODAL_TIME_HISTORY":
        if validate_exact_keys(units, {"force"}, "units", issues):
            force_unit = units.get("force")
            if force_unit not in _ALLOWED_FORCE_UNITS:
                issues.append(
                    issue(
                        "ANALYSIS_SPEC_UNSUPPORTED_UNIT",
                        "units.force",
                        f"Unsupported force unit: {force_unit!r}",
                    )
                )
        return
    if excitation_type == "UNIFORM_BASE_EXCITATION":
        validate_exact_keys(units, set(), "units", issues)


def _validate_excitation(value: Any, issues: list[dict[str, str]]) -> str | None:
    if not isinstance(value, dict):
        validate_exact_keys(value, {"type"}, "definition.excitation", issues)
        return None

    excitation_type = value.get("type")
    if excitation_type == "NODAL_TIME_HISTORY":
        validate_exact_keys(
            value,
            {"type", "nodeId", "component", "quantity", "loadArtifact"},
            "definition.excitation",
            issues,
        )
        validate_positive_target_id(
            value.get("nodeId"),
            "definition.excitation.nodeId",
            issues,
        )
        if value.get("component") not in {"X", "Y"} or value.get("quantity") != "FORCE":
            issues.append(
                issue(
                    "ANALYSIS_SPEC_UNSUPPORTED_TRANSIENT_EXCITATION",
                    "definition.excitation",
                    "NODAL_TIME_HISTORY requires component X/Y and quantity FORCE",
                )
            )
        _validate_artifact(
            value.get("loadArtifact"),
            path="definition.excitation.loadArtifact",
            issues=issues,
        )
        return excitation_type

    if excitation_type == "UNIFORM_BASE_EXCITATION":
        validate_exact_keys(
            value,
            {"type", "component", "quantity", "loadArtifact"},
            "definition.excitation",
            issues,
        )
        if value.get("component") not in {"X", "Y"} or value.get("quantity") != "ACCELERATION":
            issues.append(
                issue(
                    "ANALYSIS_SPEC_UNSUPPORTED_TRANSIENT_EXCITATION",
                    "definition.excitation",
                    "UNIFORM_BASE_EXCITATION requires component X/Y and quantity ACCELERATION",
                )
            )
        _validate_artifact(
            value.get("loadArtifact"),
            path="definition.excitation.loadArtifact",
            issues=issues,
        )
        return excitation_type

    validate_exact_keys(value, {"type"}, "definition.excitation", issues)
    issues.append(
        issue(
            "ANALYSIS_SPEC_UNSUPPORTED_TRANSIENT_EXCITATION",
            "definition.excitation.type",
            f"Unsupported transient excitation type: {excitation_type!r}",
        )
    )
    return None


def _is_supported_response(request: dict[str, Any], excitation_type: str | None) -> bool:
    target = request.get("target")
    if not isinstance(target, dict):
        return False

    quantity = request.get("quantity")
    target_type = target.get("type")
    component = request.get("component")
    has_location = "location" in request
    location = request.get("location")

    if quantity in _NODE_XY_QUANTITIES:
        return target_type == "NODE" and component in {"X", "Y"} and not has_location
    if quantity == "REACTION_MOMENT":
        return target_type == "NODE" and component == "Z" and not has_location
    if quantity == "GENERALIZED_FORCE":
        return (
            target_type == "ELEMENT"
            and component in {"N", "VY", "MZ"}
            and has_location
            and location in {"END_I", "END_J"}
        )
    if quantity == "ACCELERATION":
        return (
            excitation_type == "NODAL_TIME_HISTORY"
            and target_type == "NODE"
            and component in {"X", "Y"}
            and not has_location
        )
    if quantity in _BASE_ACCELERATION_QUANTITIES:
        return (
            excitation_type == "UNIFORM_BASE_EXCITATION"
            and target_type == "NODE"
            and component in {"X", "Y"}
            and not has_location
        )
    return False


def _validate_result_requests(
    requests: Any,
    *,
    excitation_type: str | None,
    issues: list[dict[str, str]],
) -> None:
    if not isinstance(requests, list):
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_SCHEMA",
                "resultRequests",
                "resultRequests must be an array",
            )
        )
        return
    if not requests:
        issues.append(
            issue(
                "ANALYSIS_SPEC_INVALID_SCHEMA",
                "resultRequests",
                "resultRequests must contain at least one request",
            )
        )
        return

    seen_request_ids: set[str] = set()
    for index, request in enumerate(requests):
        path = f"resultRequests[{index}]"
        quantity = request.get("quantity") if isinstance(request, dict) else None
        expected = {"requestId", "quantity", "target", "component"}
        if quantity == "GENERALIZED_FORCE":
            expected.add("location")
        if not validate_exact_keys(request, expected, path, issues):
            continue

        request_id = validate_id_token(request.get("requestId"), f"{path}.requestId", issues)
        if request_id is not None:
            if request_id in seen_request_ids:
                issues.append(
                    issue(
                        "ANALYSIS_SPEC_DUPLICATE_ID",
                        f"{path}.requestId",
                        f"Duplicate requestId {request_id!r}",
                    )
                )
            else:
                seen_request_ids.add(request_id)

        target = request.get("target")
        if validate_exact_keys(target, {"type", "id"}, f"{path}.target", issues):
            validate_positive_target_id(target.get("id"), f"{path}.target.id", issues)

        if not _is_supported_response(request, excitation_type):
            issues.append(
                issue(
                    "ANALYSIS_SPEC_UNSUPPORTED_TRANSIENT_RESPONSE",
                    path,
                    "Result request is outside the EngineeringAnalysisSpec V2 TRANSIENT whitelist",
                )
            )


def validate_v2_transient(spec: dict[str, Any], issues: list[dict[str, str]]) -> None:
    definition = spec.get("definition")
    if not validate_exact_keys(
        definition,
        {"time", "damping", "excitation"},
        "definition",
        issues,
    ):
        return

    _validate_time(definition.get("time"), issues)
    _validate_damping(definition.get("damping"), issues)
    excitation_type = _validate_excitation(definition.get("excitation"), issues)
    _validate_units(spec, excitation_type, issues)
    _validate_result_requests(
        spec.get("resultRequests"),
        excitation_type=excitation_type,
        issues=issues,
    )
