from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from fem_core.analysis_requirements.evidence import (
    validate_fact_evidence,
    validate_intent_evidence,
)
from fem_core.analysis_requirements.schema import (
    DRAFT_PROFILE,
    validate_analysis_requirement_draft,
)
from fem_core.analysis_spec import validate_engineering_analysis_spec
from fem_core.analysis_spec.transient_artifact import (
    read_transient_load_artifact,
    seconds_to_model_time_factor,
)
from fem_core.errors import FemCoreError
from fem_core.model_spec import validate_engineering_model_spec
from fem_core.pathing import resolve_workspace_file, workspace_relative_path
from fem_core.semantic_roles import inspect_semantic_roles

COMPLETION_SCHEMA = "FEMAGENT_ANALYSIS_REQUIREMENT_COMPLETION_V1"


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _gap(code: str, subject: str, message: str) -> dict[str, str]:
    return {"code": code, "subject": subject, "message": message}


def _base_report(requirement_fingerprint: str | None) -> dict[str, Any]:
    return {
        "schema": COMPLETION_SCHEMA,
        "profile": DRAFT_PROFILE,
        "status": "INCOMPLETE",
        "acceptedFacts": [],
        "derivedFacts": [],
        "context": {
            "modelSpec": None,
            "loadArtifact": None,
            "semantic": None,
        },
        "issues": [],
        "missing": [],
        "ambiguous": [],
        "conflicts": [],
        "candidateAnalysisSpec": None,
        "analysisSpecValidation": None,
        "analysisSpecFingerprint": None,
        "requirementFingerprint": requirement_fingerprint,
    }


def _invalid_context_report(
    report: dict[str, Any],
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report["status"] = "INVALID_CONTEXT"
    issue: dict[str, Any] = {
        "code": code,
        "subject": "context",
        "message": message,
    }
    if details:
        issue["details"] = details
    report["issues"] = [issue]
    return report


def _select_single_fact(
    facts: list[dict[str, Any]],
    kind: str,
) -> tuple[dict[str, Any] | None, bool]:
    matches = [fact for fact in facts if fact["kind"] == kind]
    if len(matches) == 1:
        return matches[0], False
    return None, len(matches) > 1


def _result_fact_key(fact: dict[str, Any]) -> str:
    return _canonical_hash(
        {
            "quantity": fact["quantity"],
            "target": fact["target"],
            "component": fact.get("component"),
        }
    )


def _dedupe_result_facts(
    facts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for fact in facts:
        key = _result_fact_key(fact)
        if key in seen:
            continue
        seen.add(key)
        result.append(copy.deepcopy(fact))
    return result


def _prepare_load_context(
    workspace: Path,
    load_artifact_path: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    path = resolve_workspace_file(workspace, load_artifact_path)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    relative = workspace_relative_path(workspace, path)
    evidence = read_transient_load_artifact(
        workspace,
        {"path": relative, "sha256": digest},
    )
    context = {
        "path": relative,
        "sha256": digest,
        "format": evidence["format"],
        "sampleCount": evidence["sampleCount"],
        "dtS": evidence["dtS"],
        "timeStartS": evidence["timeStartS"],
        "timeEndS": evidence["timeEndS"],
        "loadKind": evidence["loadKind"],
        "applicationType": evidence["applicationType"],
        "component": evidence["component"],
        "quantity": evidence["quantity"],
        "unit": evidence["unit"],
        "channelId": evidence["channelId"],
    }
    return context, {"path": relative, "sha256": digest}


def _explicit_context_conflicts(
    *,
    load_context: dict[str, Any],
    excitation_component: str,
) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    expected = {
        "loadKind": "EARTHQUAKE",
        "applicationType": "UNIFORM_EXCITATION",
        "quantity": "ACCELERATION",
        "unit": "m/s2",
        "component": excitation_component,
    }
    for field, value in expected.items():
        if load_context.get(field) != value:
            conflicts.append(
                _gap(
                    "ANALYSIS_REQUIREMENT_CONTEXT_CONFLICT",
                    f"loadArtifact.{field}",
                    f"Context-bound load artifact has {field}={load_context.get(field)!r}, expected {value!r}",
                )
            )
    if not math.isclose(
        float(load_context["timeStartS"]),
        0.0,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        conflicts.append(
            _gap(
                "ANALYSIS_REQUIREMENT_CONTEXT_CONFLICT",
                "loadArtifact.timeStartS",
                "Uniform-base AnalysisSpec completion requires the canonical load artifact to start at time zero",
            )
        )
    return conflicts


def _model_node_ids(model_spec: dict[str, Any]) -> set[int]:
    return {
        int(item["id"])
        for item in model_spec["nodes"]
        if isinstance(item, dict)
        and isinstance(item.get("id"), int)
        and not isinstance(item.get("id"), bool)
    }


def _constraint_map(model_spec: dict[str, Any]) -> dict[int, set[str]]:
    result: dict[int, set[str]] = {}
    for item in model_spec["constraints"]:
        if not isinstance(item, dict):
            continue
        node_id = item.get("nodeId")
        dofs = item.get("dofs")
        if isinstance(node_id, int) and isinstance(dofs, list):
            result[node_id] = {str(dof) for dof in dofs}
    return result


def _semantic_role_candidates(
    workspace: Path,
    semantic_context: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    inspection = inspect_semantic_roles(
        workspace,
        model_path=str(semantic_context["modelPath"]),
        manifest_path=str(semantic_context["manifestPath"]),
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for role in inspection["roles"]:
        grouped.setdefault(str(role["roleType"]), []).append(role)
    for roles in grouped.values():
        roles.sort(key=lambda role: str(role["roleId"]))
    return grouped


def _resolve_result_target(
    *,
    fact: dict[str, Any],
    node_ids: set[int],
    semantic_roles: dict[str, list[dict[str, Any]]] | None,
    missing: list[dict[str, str]],
    ambiguous: list[dict[str, Any]],
    conflicts: list[dict[str, str]],
    derived: list[dict[str, Any]],
) -> dict[str, Any] | None:
    target = fact["target"]
    if target["type"] == "NODE":
        node_id = int(target["id"])
        if node_id not in node_ids:
            conflicts.append(
                _gap(
                    "ANALYSIS_REQUIREMENT_CONTEXT_CONFLICT",
                    f"result.{fact['quantity']}.target",
                    f"Explicit result target node {node_id} is absent from the validated ModelSpec",
                )
            )
            return None
        return {"type": "NODE", "id": node_id}

    role_type = str(target["roleType"])
    if semantic_roles is None:
        missing.append(
            _gap(
                "ANALYSIS_REQUIREMENT_CONTEXT_MISSING",
                f"semanticContext.{role_type}",
                f"Semantic context is required to resolve role type {role_type}",
            )
        )
        return None
    matches = semantic_roles.get(role_type, [])
    if not matches:
        missing.append(
            _gap(
                "ANALYSIS_REQUIREMENT_ROLE_MISSING",
                f"semanticRole.{role_type}",
                f"No explicit semantic role of type {role_type} is declared for the current Model Bundle",
            )
        )
        return None
    if len(matches) > 1:
        ambiguous.append(
            {
                "code": "ANALYSIS_REQUIREMENT_ROLE_AMBIGUOUS",
                "subject": f"semanticRole.{role_type}",
                "message": f"Multiple explicit semantic roles of type {role_type} are available",
                "candidates": [str(item["roleId"]) for item in matches],
            }
        )
        return None

    resolved = matches[0]
    entity = resolved["entity"]
    if entity.get("type") != "NODE":
        conflicts.append(
            _gap(
                "ANALYSIS_REQUIREMENT_CONTEXT_CONFLICT",
                f"semanticRole.{role_type}",
                f"V1 analysis completion requires NODE semantic targets; resolved role {resolved['roleId']} is {entity.get('type')}",
            )
        )
        return None
    node_id = int(entity["id"])
    if node_id not in node_ids:
        conflicts.append(
            _gap(
                "ANALYSIS_REQUIREMENT_CONTEXT_CONFLICT",
                f"semanticRole.{role_type}",
                f"Resolved semantic role node {node_id} is absent from the validated ModelSpec",
            )
        )
        return None
    derived.append(
        {
            "kind": "RESULT_TARGET",
            "source": "DETERMINISTIC_DERIVED",
            "ruleId": "SEMANTIC_ROLE_TYPE_RESOLUTION_V1",
            "roleType": role_type,
            "roleId": resolved["roleId"],
            "entity": {"type": "NODE", "id": node_id},
            "manifestSha256": resolved["manifestSha256"],
            "modelBundleFingerprint": resolved["modelBundleFingerprint"],
            "entityValidation": resolved["entityValidation"],
        }
    )
    return {"type": "NODE", "id": node_id}


def _reaction_is_supported(
    *,
    target: dict[str, Any],
    component: str,
    constraints: dict[int, set[str]],
) -> bool:
    dof = "UX" if component == "X" else "UY"
    return dof in constraints.get(int(target["id"]), set())


def complete_engineering_analysis_requirement(
    workspace: Path,
    *,
    draft: dict[str, Any],
    model_spec: dict[str, Any],
    load_artifact_path: str,
    semantic_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    schema_result = validate_analysis_requirement_draft(draft)
    if schema_result["status"] != "VALID":
        report = _base_report(requirement_fingerprint=None)
        report["status"] = "INVALID_DRAFT"
        report["issues"] = schema_result["issues"]
        return report

    normalized = schema_result["normalizedDraft"]
    requirement_fingerprint = _canonical_hash(normalized)
    report = _base_report(requirement_fingerprint)
    sources = {
        source["sourceId"]: source["text"]
        for source in normalized["sources"]
    }

    intent_result = validate_intent_evidence(
        sources=sources,
        intent=normalized["intent"],
    )
    if intent_result["issues"]:
        report["status"] = "INVALID_DRAFT"
        report["issues"] = intent_result["issues"]
        return report

    accepted: list[dict[str, Any]] = []
    for fact in normalized["facts"]:
        evidence_result = validate_fact_evidence(sources=sources, fact=fact)
        if evidence_result["issues"]:
            report["status"] = "INVALID_DRAFT"
            report["issues"].extend(evidence_result["issues"])
        else:
            accepted.append(copy.deepcopy(fact))
    if report["issues"]:
        return report
    report["acceptedFacts"] = copy.deepcopy(accepted)

    model_validation = validate_engineering_model_spec(model_spec)
    if model_validation["status"] != "VALID":
        return _invalid_context_report(
            report,
            code="ANALYSIS_REQUIREMENT_MODEL_SPEC_INVALID",
            message="Analysis completion requires a valid EngineeringModelSpec",
            details={"issues": model_validation["issues"]},
        )
    normalized_model = model_validation["normalizedSpec"]
    model_fingerprint = model_validation["modelSpecFingerprint"]
    assert isinstance(normalized_model, dict)
    assert isinstance(model_fingerprint, str)
    report["context"]["modelSpec"] = {
        "modelSpecFingerprint": model_fingerprint,
        "units": copy.deepcopy(normalized_model["units"]),
    }
    report["derivedFacts"].append(
        {
            "kind": "MODEL_SPEC_BINDING",
            "source": "CONTEXT_BOUND",
            "ruleId": "MODEL_SPEC_BINDING_V1",
            "modelSpecFingerprint": model_fingerprint,
        }
    )

    try:
        load_context, load_ref = _prepare_load_context(
            workspace,
            load_artifact_path,
        )
    except FemCoreError as exc:
        return _invalid_context_report(
            report,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
    report["context"]["loadArtifact"] = copy.deepcopy(load_context)
    report["derivedFacts"].append(
        {
            "kind": "LOAD_ARTIFACT",
            "source": "CONTEXT_BOUND",
            "ruleId": "CANONICAL_LOAD_IDENTITY_V1",
            "path": load_ref["path"],
            "sha256": load_ref["sha256"],
        }
    )

    missing: list[dict[str, str]] = []
    ambiguous: list[dict[str, Any]] = []
    conflicts: list[dict[str, str]] = []

    component_fact, component_conflict = _select_single_fact(
        accepted,
        "EXCITATION_COMPONENT",
    )
    if component_conflict:
        conflicts.append(
            _gap(
                "ANALYSIS_REQUIREMENT_FACT_CONFLICT",
                "excitation.component",
                "Multiple excitation-component facts were supplied",
            )
        )
    elif component_fact is None:
        missing.append(
            _gap(
                "ANALYSIS_REQUIREMENT_FACT_MISSING",
                "excitation.component",
                "X or Y earthquake excitation component must be explicitly stated",
            )
        )

    load_fact, load_conflict = _select_single_fact(accepted, "LOAD_SELECTION")
    if load_conflict:
        conflicts.append(
            _gap(
                "ANALYSIS_REQUIREMENT_FACT_CONFLICT",
                "loadSelection",
                "Multiple load-selection facts were supplied",
            )
        )
    elif load_fact is None:
        missing.append(
            _gap(
                "ANALYSIS_REQUIREMENT_FACT_MISSING",
                "loadSelection",
                "The user must explicitly select the context-bound earthquake record",
            )
        )

    damping_none, multiple_none = _select_single_fact(accepted, "DAMPING_NONE")
    rayleigh, multiple_rayleigh = _select_single_fact(accepted, "RAYLEIGH_DAMPING")
    if multiple_none or multiple_rayleigh or (damping_none is not None and rayleigh is not None):
        conflicts.append(
            _gap(
                "ANALYSIS_REQUIREMENT_FACT_CONFLICT",
                "damping",
                "Damping facts conflict or are duplicated",
            )
        )
        damping: dict[str, Any] | None = None
    elif damping_none is not None:
        damping = {"type": "NONE"}
    elif rayleigh is not None:
        damping = {
            "type": "RAYLEIGH",
            "alphaM": float(rayleigh["alphaM"]),
            "betaK": float(rayleigh["betaK"]),
        }
    else:
        damping = None
        missing.append(
            _gap(
                "ANALYSIS_REQUIREMENT_FACT_MISSING",
                "damping",
                "Damping must be explicit: NONE or Rayleigh alphaM/betaK; no default is assumed",
            )
        )

    if component_fact is not None:
        conflicts.extend(
            _explicit_context_conflicts(
                load_context=load_context,
                excitation_component=str(component_fact["component"]),
            )
        )

    time_factor = seconds_to_model_time_factor(
        str(normalized_model["units"]["time"])
    )
    time_step = float(load_context["dtS"]) * time_factor
    duration = float(load_context["timeEndS"]) * time_factor
    report["derivedFacts"].append(
        {
            "kind": "TRANSIENT_TIME",
            "source": "DETERMINISTIC_DERIVED",
            "ruleId": "TRANSIENT_TIME_FROM_ARTIFACT_V1",
            "timeStep": time_step,
            "duration": duration,
            "modelTimeUnit": normalized_model["units"]["time"],
        }
    )

    semantic_roles: dict[str, list[dict[str, Any]]] | None = None
    role_targets_used = any(
        fact["kind"] == "RESULT_REQUEST"
        and fact["target"]["type"] == "SEMANTIC_ROLE_TYPE"
        for fact in accepted
    )
    if role_targets_used and semantic_context is not None:
        if set(semantic_context) != {"modelPath", "manifestPath"}:
            return _invalid_context_report(
                report,
                code="ANALYSIS_REQUIREMENT_SEMANTIC_CONTEXT_INVALID",
                message="semanticContext requires exactly modelPath and manifestPath",
            )
        try:
            semantic_roles = _semantic_role_candidates(
                workspace,
                semantic_context,
            )
            report["context"]["semantic"] = {
                "modelPath": semantic_context["modelPath"],
                "manifestPath": semantic_context["manifestPath"],
            }
        except FemCoreError as exc:
            return _invalid_context_report(
                report,
                code=exc.code,
                message=exc.message,
                details=exc.details,
            )

    result_facts = _dedupe_result_facts(
        [fact for fact in accepted if fact["kind"] == "RESULT_REQUEST"]
    )
    if not result_facts:
        missing.append(
            _gap(
                "ANALYSIS_REQUIREMENT_FACT_MISSING",
                "resultRequests",
                "At least one displacement or reaction-force request must be explicit",
            )
        )

    node_ids = _model_node_ids(normalized_model)
    constraints = _constraint_map(normalized_model)
    result_requests: list[dict[str, Any]] = []
    for index, fact in enumerate(result_facts, start=1):
        component = fact.get("component")
        if component is None:
            missing.append(
                _gap(
                    "ANALYSIS_REQUIREMENT_FACT_MISSING",
                    f"resultRequests[{index - 1}].component",
                    f"{fact['quantity']} response component must be explicitly stated",
                )
            )
            continue

        target = _resolve_result_target(
            fact=fact,
            node_ids=node_ids,
            semantic_roles=semantic_roles,
            missing=missing,
            ambiguous=ambiguous,
            conflicts=conflicts,
            derived=report["derivedFacts"],
        )
        if target is None:
            continue
        if fact["quantity"] == "REACTION_FORCE" and not _reaction_is_supported(
            target=target,
            component=str(component),
            constraints=constraints,
        ):
            conflicts.append(
                _gap(
                    "ANALYSIS_REQUIREMENT_CONTEXT_CONFLICT",
                    f"resultRequests[{index - 1}]",
                    f"REACTION_FORCE {component} requires the target node's corresponding translational DOF to be constrained in ModelSpec",
                )
            )
            continue

        request = {
            "requestId": f"R{index}",
            "quantity": fact["quantity"],
            "target": target,
            "component": component,
        }
        result_requests.append(request)
        report["derivedFacts"].append(
            {
                "kind": "RESULT_REQUEST_ID",
                "source": "DETERMINISTIC_DERIVED",
                "ruleId": "ANALYSIS_REQUEST_ID_V1",
                "requestId": request["requestId"],
                "quantity": request["quantity"],
            }
        )

    report["missing"] = missing
    report["ambiguous"] = ambiguous
    report["conflicts"] = conflicts
    if conflicts:
        report["status"] = "CONFLICT"
        return report
    if missing or ambiguous:
        report["status"] = "INCOMPLETE"
        return report

    assert component_fact is not None
    assert damping is not None
    candidate = {
        "schemaVersion": "2.0",
        "kind": "engineering_analysis_spec",
        "modelSpecFingerprint": model_fingerprint,
        "analysisType": "TRANSIENT",
        "units": {},
        "definition": {
            "time": {
                "timeStep": time_step,
                "duration": duration,
            },
            "damping": damping,
            "excitation": {
                "type": "UNIFORM_BASE_EXCITATION",
                "component": component_fact["component"],
                "quantity": "ACCELERATION",
                "loadArtifact": load_ref,
            },
        },
        "resultRequests": result_requests,
    }
    validation = validate_engineering_analysis_spec(candidate)
    report["analysisSpecValidation"] = {
        "schema": validation["schema"],
        "status": validation["status"],
        "issues": copy.deepcopy(validation["issues"]),
    }
    if validation["status"] != "VALID":
        report["status"] = "INVALID_CONTEXT"
        report["issues"] = [
            {
                "code": "ANALYSIS_REQUIREMENT_CANDIDATE_INVALID",
                "subject": "candidateAnalysisSpec",
                "message": "Deterministic completion produced an invalid AnalysisSpec candidate",
                "details": {"issues": validation["issues"]},
            }
        ]
        return report

    report["status"] = "COMPLETE"
    report["candidateAnalysisSpec"] = copy.deepcopy(validation["normalizedSpec"])
    report["analysisSpecFingerprint"] = validation["analysisSpecFingerprint"]
    return report


__all__ = [
    "COMPLETION_SCHEMA",
    "complete_engineering_analysis_requirement",
]
