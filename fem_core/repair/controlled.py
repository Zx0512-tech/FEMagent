from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.workflows import prepare_earthquake_workflow

REPAIR_PLAN_SCHEMA = "FEMAGENT_CONTROLLED_REPAIR_PLAN_V1"
REPAIR_RETRY_SCHEMA = "FEMAGENT_CONTROLLED_REPAIR_RETRY_V1"

_RESULT_COMPONENT_SUBJECT = re.compile(r"^resultRequests\[(\d+)\]\.component$")


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _action(
    *,
    action_id: str,
    category: str,
    subject: str,
    message: str,
    resolution_types: list[str],
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "actionId": action_id,
        "category": category,
        "subject": subject,
        "message": message,
        "resolutionTypes": resolution_types,
    }
    if details:
        result["details"] = copy.deepcopy(details)
    return result


def _result_fact_indexes(draft: dict[str, Any]) -> list[int]:
    return [
        index
        for index, fact in enumerate(draft.get("facts", []))
        if isinstance(fact, dict) and fact.get("kind") == "RESULT_REQUEST"
    ]


def _diagnose_completion(
    workflow_input: dict[str, Any],
    completion: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    draft = workflow_input.get("draft")
    if not isinstance(draft, dict):
        return actions
    result_indexes = _result_fact_indexes(draft)

    for gap in completion.get("missing", []):
        if not isinstance(gap, dict):
            continue
        subject = str(gap.get("subject") or "")
        if subject == "damping":
            actions.append(
                _action(
                    action_id="repair_damping",
                    category="USER_INPUT",
                    subject=subject,
                    message="Damping must be explicitly confirmed; no default is allowed.",
                    resolution_types=["ADD_DAMPING_NONE", "ADD_RAYLEIGH_DAMPING"],
                )
            )
        elif subject == "excitation.component":
            actions.append(
                _action(
                    action_id="repair_excitation_component",
                    category="USER_INPUT",
                    subject=subject,
                    message="The earthquake excitation direction must be explicitly confirmed.",
                    resolution_types=["SET_EXCITATION_COMPONENT"],
                    details={"allowedValues": ["X", "Y"]},
                )
            )
        elif subject == "loadSelection":
            actions.append(
                _action(
                    action_id="repair_load_selection",
                    category="USER_INPUT",
                    subject=subject,
                    message="The user must explicitly confirm the selected canonical earthquake record.",
                    resolution_types=["ADD_LOAD_SELECTION"],
                )
            )
        else:
            match = _RESULT_COMPONENT_SUBJECT.match(subject)
            if match:
                result_index = int(match.group(1))
                if result_index < len(result_indexes):
                    actions.append(
                        _action(
                            action_id=f"repair_result_component_{result_index}",
                            category="USER_INPUT",
                            subject=subject,
                            message="The response component must be explicitly confirmed.",
                            resolution_types=["SET_RESULT_COMPONENT"],
                            details={
                                "allowedValues": ["X", "Y"],
                                "draftFactIndex": result_indexes[result_index],
                            },
                        )
                    )
            elif subject.startswith("semanticContext."):
                actions.append(
                    _action(
                        action_id="repair_semantic_context",
                        category="USER_INPUT",
                        subject=subject,
                        message="A current explicit Semantic Role context is required.",
                        resolution_types=["PROVIDE_SEMANTIC_CONTEXT"],
                    )
                )
            elif subject.startswith("semanticRole."):
                actions.append(
                    _action(
                        action_id=f"manual_{len(actions)+1}",
                        category="MANUAL_ENGINEERING_CHANGE",
                        subject=subject,
                        message=(
                            "The requested semantic role is not deterministically available. "
                            "Update the requirement or explicit Semantic Role Manifest; FEMagent will not guess a node."
                        ),
                        resolution_types=[],
                    )
                )
            else:
                actions.append(
                    _action(
                        action_id=f"manual_{len(actions)+1}",
                        category="MANUAL_ENGINEERING_CHANGE",
                        subject=subject or "analysisRequirement",
                        message=str(gap.get("message") or "Manual engineering clarification is required."),
                        resolution_types=[],
                    )
                )

    for ambiguity in completion.get("ambiguous", []):
        if not isinstance(ambiguity, dict):
            continue
        actions.append(
            _action(
                action_id=f"ambiguity_{len(actions)+1}",
                category="MANUAL_ENGINEERING_CHANGE",
                subject=str(ambiguity.get("subject") or "semanticRole"),
                message=(
                    "Multiple explicit engineering targets match the request. "
                    "Clarify the requirement or update semantic context; no candidate is selected automatically."
                ),
                resolution_types=[],
                details={"candidates": copy.deepcopy(ambiguity.get("candidates", []))},
            )
        )

    for conflict in completion.get("conflicts", []):
        if not isinstance(conflict, dict):
            continue
        subject = str(conflict.get("subject") or "")
        if subject.startswith("loadArtifact."):
            actions.append(
                _action(
                    action_id="repair_load_artifact",
                    category="USER_INPUT",
                    subject=subject,
                    message=(
                        "The selected canonical load conflicts with the explicit analysis requirement. "
                        "Select a different verified canonical load artifact or update the requirement."
                    ),
                    resolution_types=["REPLACE_LOAD_ARTIFACT"],
                )
            )
        elif subject.startswith("resultRequests"):
            actions.append(
                _action(
                    action_id=f"manual_{len(actions)+1}",
                    category="MANUAL_ENGINEERING_CHANGE",
                    subject=subject,
                    message=(
                        "The requested response conflicts with deterministic model constraints. "
                        "Update the model or requested response; constraints are never invented."
                    ),
                    resolution_types=["REPLACE_MODEL_SPEC"],
                )
            )
        else:
            actions.append(
                _action(
                    action_id=f"manual_{len(actions)+1}",
                    category="MANUAL_ENGINEERING_CHANGE",
                    subject=subject or "analysisRequirement",
                    message=str(conflict.get("message") or "Manual engineering correction is required."),
                    resolution_types=[],
                )
            )

    if completion.get("status") in {"INVALID_DRAFT", "INVALID_CONTEXT"}:
        for issue in completion.get("issues", []):
            if not isinstance(issue, dict):
                continue
            actions.append(
                _action(
                    action_id=f"invalid_{len(actions)+1}",
                    category="MANUAL_ENGINEERING_CHANGE",
                    subject=str(issue.get("subject") or "context"),
                    message=str(issue.get("message") or "Invalid evidence/context must be corrected."),
                    resolution_types=[],
                )
            )
    return actions


def _diagnose_readiness(preparation: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    readiness = preparation.get("analysisReadiness")
    if not isinstance(readiness, dict):
        return actions
    for issue in readiness.get("issues", []):
        if not isinstance(issue, dict) or issue.get("severity") != "ERROR":
            continue
        code = str(issue.get("code") or "")
        if code == "EARTHQUAKE_WORKFLOW_OPENSEES_EXCITED_MASS_UNPROVEN":
            actions.append(
                _action(
                    action_id="repair_model_mass",
                    category="MANUAL_ENGINEERING_CHANGE",
                    subject="modelSpec.nodalMasses",
                    message=(
                        "Positive nodal mass in the excited direction is required. "
                        "Provide a revised ModelSpec based on engineering evidence; FEMagent will not invent mass."
                    ),
                    resolution_types=["REPLACE_MODEL_SPEC"],
                )
            )
        else:
            actions.append(
                _action(
                    action_id=f"readiness_{len(actions)+1}",
                    category="MANUAL_ENGINEERING_CHANGE",
                    subject=str(issue.get("path") or "analysisReadiness"),
                    message=str(issue.get("message") or "Analysis readiness requires engineering correction."),
                    resolution_types=[],
                    details={"code": code},
                )
            )
    return actions


def _diagnose_warnings(preparation: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for warning in preparation.get("warnings", []):
        if not isinstance(warning, dict):
            continue
        code = str(warning.get("code") or "")
        if code == "EARTHQUAKE_WORKFLOW_ANSYS_MODEL_PATH_REQUIRED":
            actions.append(
                _action(
                    action_id="repair_ansys_model_path",
                    category="USER_INPUT",
                    subject="solverModelPath",
                    message="Provide the workspace-relative ANSYS APDL entrypoint.",
                    resolution_types=["SET_ANSYS_MODEL_PATH"],
                )
            )
    return actions


def _diagnose_preflight(preparation: dict[str, Any]) -> list[dict[str, Any]]:
    preflight = preparation.get("preflight")
    if not isinstance(preflight, dict) or preflight.get("status") == "READY":
        return []
    actions: list[dict[str, Any]] = []
    for check in preflight.get("checks", []):
        if not isinstance(check, dict) or check.get("status") != "FAILED":
            continue
        code = str(check.get("code") or "")
        if code == "SOLVER_AVAILABLE":
            actions.append(
                _action(
                    action_id="operator_solver_available",
                    category="OPERATOR_ACTION",
                    subject="solver.runtime",
                    message="Restore/configure the requested mature solver runtime, then rerun preparation.",
                    resolution_types=[],
                    details={"checkCode": code},
                )
            )
        elif code == "BUILD_ONLY_INSPECTION":
            actions.append(
                _action(
                    action_id="operator_build_inspection",
                    category="OPERATOR_ACTION",
                    subject="solver.preflight",
                    message="Inspect the build-only solver diagnostics; FEMagent will not mutate the model to force preflight success.",
                    resolution_types=[],
                    details={"checkCode": code},
                )
            )
        else:
            actions.append(
                _action(
                    action_id=f"preflight_{len(actions)+1}",
                    category="MANUAL_ENGINEERING_CHANGE",
                    subject="solver.preflight",
                    message=f"Preflight check {code or 'unknown'} failed and requires explicit correction.",
                    resolution_types=[],
                    details={"checkCode": code},
                )
            )
    return actions


def plan_controlled_repair(
    *,
    workflow_input: dict[str, Any],
    failed_preparation: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(workflow_input, dict) or not isinstance(failed_preparation, dict):
        raise FemCoreError(
            "CONTROLLED_REPAIR_INVALID_INPUT",
            "workflowInput and failedPreparation must be JSON objects",
        )
    status = failed_preparation.get("status")
    if status == "READY_FOR_CONFIRMATION":
        actions: list[dict[str, Any]] = []
        plan_status = "NO_REPAIR_NEEDED"
    elif status not in {"NEEDS_INPUT", "ANALYSIS_NOT_READY", "PREFLIGHT_BLOCKED"}:
        actions = []
        plan_status = "UNSUPPORTED_FAILURE"
    else:
        actions = []
        completion = failed_preparation.get("analysisCompletion")
        if isinstance(completion, dict) and completion.get("status") != "COMPLETE":
            actions.extend(_diagnose_completion(workflow_input, completion))
        actions.extend(_diagnose_readiness(failed_preparation))
        actions.extend(_diagnose_warnings(failed_preparation))
        actions.extend(_diagnose_preflight(failed_preparation))

        categories = {item["category"] for item in actions}
        if "MANUAL_ENGINEERING_CHANGE" in categories:
            plan_status = "MANUAL_ENGINEERING_CHANGE_REQUIRED"
        elif "USER_INPUT" in categories:
            plan_status = "USER_ACTION_REQUIRED"
        elif "OPERATOR_ACTION" in categories:
            plan_status = "OPERATOR_ACTION_REQUIRED"
        else:
            plan_status = "UNSUPPORTED_FAILURE"

    input_fingerprint = _hash(workflow_input)
    failure_fingerprint = _hash(failed_preparation)
    action_fingerprint = _hash(actions)
    plan_fingerprint = _hash(
        {
            "inputFingerprint": input_fingerprint,
            "failureFingerprint": failure_fingerprint,
            "actionFingerprint": action_fingerprint,
        }
    )
    return {
        "schema": REPAIR_PLAN_SCHEMA,
        "status": plan_status,
        "inputFingerprint": input_fingerprint,
        "failureFingerprint": failure_fingerprint,
        "actionFingerprint": action_fingerprint,
        "planFingerprint": plan_fingerprint,
        "actions": actions,
        "rules": {
            "solverExecutionAllowed": False,
            "sourceFileMutationAllowed": False,
            "engineeringFactInferenceAllowed": False,
            "userConfirmationRequiredForResolution": True,
        },
    }


def _append_source_and_fact(
    draft: dict[str, Any],
    *,
    action_id: str,
    source_text: str,
    quote: str,
    fact: dict[str, Any],
) -> None:
    source_id = f"repair_{action_id}"
    sources = draft.setdefault("sources", [])
    sources[:] = [
        item
        for item in sources
        if not (isinstance(item, dict) and item.get("sourceId") == source_id)
    ]
    sources.append(
        {"sourceId": source_id, "kind": "USER_MESSAGE", "text": source_text}
    )
    fact["source"] = "USER_EXPLICIT"
    fact["evidence"] = {"sourceId": source_id, "quote": quote}
    draft.setdefault("facts", []).append(fact)


def _require_text(resolution: dict[str, Any], field: str) -> str:
    value = resolution.get(field)
    if not isinstance(value, str) or not value.strip():
        raise FemCoreError(
            "CONTROLLED_REPAIR_INVALID_RESOLUTION",
            f"Repair resolution field {field} must be a non-empty string",
        )
    return value


def _apply_resolution(
    workflow_input: dict[str, Any],
    action: dict[str, Any],
    resolution: dict[str, Any],
) -> None:
    resolution_type = resolution.get("type")
    if resolution_type not in action["resolutionTypes"]:
        raise FemCoreError(
            "CONTROLLED_REPAIR_INVALID_RESOLUTION",
            "Resolution type is not admitted by the selected repair action",
            details={
                "actionId": action["actionId"],
                "resolutionType": resolution_type,
                "allowed": action["resolutionTypes"],
            },
        )
    draft = workflow_input.get("draft")
    if not isinstance(draft, dict):
        raise FemCoreError(
            "CONTROLLED_REPAIR_INVALID_RESOLUTION",
            "Workflow input draft is missing",
        )

    if resolution_type == "ADD_DAMPING_NONE":
        _append_source_and_fact(
            draft,
            action_id=action["actionId"],
            source_text=_require_text(resolution, "sourceText"),
            quote=_require_text(resolution, "quote"),
            fact={"kind": "DAMPING_NONE"},
        )
    elif resolution_type == "ADD_RAYLEIGH_DAMPING":
        alpha = resolution.get("alphaM")
        beta = resolution.get("betaK")
        if not isinstance(alpha, (int, float)) or isinstance(alpha, bool) or float(alpha) < 0:
            raise FemCoreError(
                "CONTROLLED_REPAIR_INVALID_RESOLUTION",
                "alphaM must be an explicit non-negative number",
            )
        if not isinstance(beta, (int, float)) or isinstance(beta, bool) or float(beta) < 0:
            raise FemCoreError(
                "CONTROLLED_REPAIR_INVALID_RESOLUTION",
                "betaK must be an explicit non-negative number",
            )
        _append_source_and_fact(
            draft,
            action_id=action["actionId"],
            source_text=_require_text(resolution, "sourceText"),
            quote=_require_text(resolution, "quote"),
            fact={
                "kind": "RAYLEIGH_DAMPING",
                "alphaM": float(alpha),
                "betaK": float(beta),
            },
        )
    elif resolution_type == "SET_EXCITATION_COMPONENT":
        component = resolution.get("component")
        if component not in {"X", "Y"}:
            raise FemCoreError(
                "CONTROLLED_REPAIR_INVALID_RESOLUTION",
                "Excitation component must be X or Y",
            )
        _append_source_and_fact(
            draft,
            action_id=action["actionId"],
            source_text=_require_text(resolution, "sourceText"),
            quote=_require_text(resolution, "quote"),
            fact={"kind": "EXCITATION_COMPONENT", "component": component},
        )
    elif resolution_type == "ADD_LOAD_SELECTION":
        _append_source_and_fact(
            draft,
            action_id=action["actionId"],
            source_text=_require_text(resolution, "sourceText"),
            quote=_require_text(resolution, "quote"),
            fact={"kind": "LOAD_SELECTION"},
        )
    elif resolution_type == "SET_RESULT_COMPONENT":
        component = resolution.get("component")
        if component not in {"X", "Y"}:
            raise FemCoreError(
                "CONTROLLED_REPAIR_INVALID_RESOLUTION",
                "Result component must be X or Y",
            )
        fact_index = action.get("details", {}).get("draftFactIndex")
        facts = draft.get("facts")
        if (
            not isinstance(fact_index, int)
            or not isinstance(facts, list)
            or fact_index < 0
            or fact_index >= len(facts)
            or not isinstance(facts[fact_index], dict)
            or facts[fact_index].get("kind") != "RESULT_REQUEST"
        ):
            raise FemCoreError(
                "CONTROLLED_REPAIR_STALE_PLAN",
                "Result repair action no longer points to the same draft fact",
            )
        source_id = f"repair_{action['actionId']}"
        source_text = _require_text(resolution, "sourceText")
        quote = _require_text(resolution, "quote")
        draft.setdefault("sources", []).append(
            {"sourceId": source_id, "kind": "USER_MESSAGE", "text": source_text}
        )
        facts[fact_index]["component"] = component
        facts[fact_index]["evidence"] = {"sourceId": source_id, "quote": quote}
    elif resolution_type == "SET_ANSYS_MODEL_PATH":
        workflow_input["solverModelPath"] = _require_text(resolution, "solverModelPath")
    elif resolution_type == "REPLACE_LOAD_ARTIFACT":
        workflow_input["loadArtifactPath"] = _require_text(resolution, "loadArtifactPath")
    elif resolution_type == "REPLACE_MODEL_SPEC":
        model_spec = resolution.get("modelSpec")
        if not isinstance(model_spec, dict):
            raise FemCoreError(
                "CONTROLLED_REPAIR_INVALID_RESOLUTION",
                "REPLACE_MODEL_SPEC requires a complete modelSpec object",
            )
        workflow_input["modelSpec"] = copy.deepcopy(model_spec)
    elif resolution_type == "PROVIDE_SEMANTIC_CONTEXT":
        context = resolution.get("semanticContext")
        if not isinstance(context, dict) or set(context) != {"modelPath", "manifestPath"}:
            raise FemCoreError(
                "CONTROLLED_REPAIR_INVALID_RESOLUTION",
                "semanticContext requires exactly modelPath and manifestPath",
            )
        workflow_input["semanticContext"] = copy.deepcopy(context)
    else:
        raise FemCoreError(
            "CONTROLLED_REPAIR_INVALID_RESOLUTION",
            f"Unsupported repair resolution type: {resolution_type!r}",
        )


def retry_controlled_repair(
    workspace: Path,
    *,
    workflow_input: dict[str, Any],
    failed_preparation: dict[str, Any],
    plan_fingerprint: str,
    resolutions: list[dict[str, Any]],
) -> dict[str, Any]:
    plan = plan_controlled_repair(
        workflow_input=workflow_input,
        failed_preparation=failed_preparation,
    )
    if plan["planFingerprint"] != plan_fingerprint:
        raise FemCoreError(
            "CONTROLLED_REPAIR_STALE_PLAN",
            "Repair plan fingerprint does not match the current workflow input/failure state",
            details={
                "expected": plan["planFingerprint"],
                "received": plan_fingerprint,
            },
        )
    if plan["status"] == "NO_REPAIR_NEEDED":
        return {
            "schema": REPAIR_RETRY_SCHEMA,
            "status": "RECOVERED_TO_READY",
            "repairPlan": plan,
            "appliedResolutions": [],
            "workflowInput": copy.deepcopy(workflow_input),
            "preparation": copy.deepcopy(failed_preparation),
        }

    actions = {item["actionId"]: item for item in plan["actions"]}
    patched = copy.deepcopy(workflow_input)
    applied: list[dict[str, Any]] = []
    seen: set[str] = set()
    for resolution in resolutions:
        if not isinstance(resolution, dict):
            raise FemCoreError(
                "CONTROLLED_REPAIR_INVALID_RESOLUTION",
                "Each repair resolution must be a JSON object",
            )
        action_id = resolution.get("actionId")
        if not isinstance(action_id, str) or action_id not in actions:
            raise FemCoreError(
                "CONTROLLED_REPAIR_INVALID_RESOLUTION",
                "Repair resolution references an unknown actionId",
                details={"actionId": action_id},
            )
        if action_id in seen:
            raise FemCoreError(
                "CONTROLLED_REPAIR_INVALID_RESOLUTION",
                "Each repair action may be resolved at most once per retry",
                details={"actionId": action_id},
            )
        seen.add(action_id)
        _apply_resolution(patched, actions[action_id], resolution)
        applied.append(
            {
                "actionId": action_id,
                "type": resolution.get("type"),
                "source": "USER_CONFIRMED",
            }
        )

    preparation = prepare_earthquake_workflow(
        workspace,
        solver=_require_text(patched, "solver"),
        draft=patched["draft"],
        model_spec=patched["modelSpec"],
        load_artifact_path=_require_text(patched, "loadArtifactPath"),
        semantic_context=patched.get("semanticContext"),
        solver_model_path=patched.get("solverModelPath"),
    )
    return {
        "schema": REPAIR_RETRY_SCHEMA,
        "status": (
            "RECOVERED_TO_READY"
            if preparation.get("status") == "READY_FOR_CONFIRMATION"
            else "RETRY_STILL_BLOCKED"
        ),
        "repairPlan": plan,
        "appliedResolutions": applied,
        "workflowInput": patched,
        "preparation": preparation,
    }


__all__ = [
    "REPAIR_PLAN_SCHEMA",
    "REPAIR_RETRY_SCHEMA",
    "plan_controlled_repair",
    "retry_controlled_repair",
]
