from __future__ import annotations

import ast
import importlib.util
from hashlib import sha256
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError
from fem_core.model_bundle import discover_bundle
from fem_core.pathing import resolve_workspace_file, workspace_relative_path

_MAX_PYTHON_MODEL_BYTES = 5 * 1024 * 1024
_OPENSEES_BUILD_CALLS = {
    "model",
    "node",
    "element",
    "fix",
    "mass",
    "uniaxialMaterial",
    "section",
    "geomTransf",
}
_OPENSEES_ANALYSIS_CALLS = {
    "timeSeries",
    "pattern",
    "constraints",
    "numberer",
    "system",
    "integrator",
    "algorithm",
    "analysis",
    "analyze",
    "eigen",
}
_FILE_READ_CALLS = {"open", "read_csv", "loadtxt", "genfromtxt"}
_BLOCKED_IMPORT_ROOTS = {"subprocess", "socket", "requests", "urllib", "ctypes"}


def _literal_int(node: ast.AST | None) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return int(node.value)
    return None


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_name(node: ast.Call) -> tuple[str | None, str | None]:
    if isinstance(node.func, ast.Name):
        return None, node.func.id
    if isinstance(node.func, ast.Attribute):
        owner = node.func.value
        if isinstance(owner, ast.Name):
            return owner.id, node.func.attr
        if isinstance(owner, ast.Attribute):
            parts: list[str] = []
            current: ast.AST = owner
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
                return ".".join(reversed(parts)), node.func.attr
    return None, None


def _local_module_target(workspace: Path, source: Path, module: str) -> Path | None:
    if not module:
        return None
    parts = module.split(".")
    candidates = [
        source.parent.joinpath(*parts).with_suffix(".py"),
        source.parent.joinpath(*parts, "__init__.py"),
        workspace.joinpath(*parts).with_suffix(".py"),
        workspace.joinpath(*parts, "__init__.py"),
    ]
    root = workspace.resolve()
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        if resolved.is_file():
            return resolved
    return None


def _external_import(module: str) -> bool:
    root = module.split(".", 1)[0]
    if root == "openseespy":
        return True
    spec = importlib.util.find_spec(root)
    return spec is not None


def _scan_python_file(
    workspace: Path,
    path: Path,
    *,
    visited: set[str],
    dependencies: list[dict[str, Any]],
    safety_findings: list[dict[str, Any]],
    aggregate: dict[str, Any],
) -> None:
    relative = workspace_relative_path(workspace, path)
    if relative in visited:
        return
    visited.add(relative)
    content = path.read_bytes()
    if not content:
        raise FemCoreError("EMPTY_MODEL_FILE", "The OpenSees Python model file is empty")
    if len(content) > _MAX_PYTHON_MODEL_BYTES:
        raise FemCoreError("MODEL_FILE_TOO_LARGE", "OpenSees Python source exceeds the 5 MiB static inspection limit")
    try:
        text = content.decode("utf-8-sig")
        tree = ast.parse(text, filename=relative)
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise FemCoreError(
            "INVALID_PYTHON_MODEL",
            "OpenSees Python model must be valid UTF-8 Python source",
            details={"path": relative},
        ) from exc

    opensees_aliases = aggregate.setdefault("openseesAliases", set())
    node_ids: set[int] = aggregate.setdefault("nodeIds", set())
    element_ids: set[int] = aggregate.setdefault("elementIds", set())
    api_signals: dict[str, int] = aggregate.setdefault("apiSignals", {})

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if alias.name == "openseespy.opensees":
                    opensees_aliases.add(alias.asname or "openseespy.opensees")
                    aggregate["hasOpenSeesImport"] = True
                if root in _BLOCKED_IMPORT_ROOTS:
                    code = "SUBPROCESS" if root == "subprocess" else "NETWORK" if root in {"socket", "requests", "urllib"} else "CTYPES"
                    safety_findings.append(
                        {"path": relative, "line": node.lineno, "code": code, "severity": "ERROR"}
                    )
                local = _local_module_target(workspace, path, alias.name)
                if local is not None:
                    target = workspace_relative_path(workspace, local)
                    dependencies.append(
                        {
                            "source": relative,
                            "reference": alias.name,
                            "target": str(Path(target).relative_to(Path(relative).parent)),
                            "type": "PYTHON_IMPORT",
                            "role": "PYTHON_MODULE",
                        }
                    )
                    _scan_python_file(
                        workspace,
                        local,
                        visited=visited,
                        dependencies=dependencies,
                        safety_findings=safety_findings,
                        aggregate=aggregate,
                    )
                elif _external_import(alias.name):
                    dependencies.append(
                        {
                            "source": relative,
                            "reference": alias.name,
                            "target": None,
                            "type": "PYTHON_IMPORT",
                            "role": None,
                            "status": "EXTERNAL_PACKAGE",
                        }
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".", 1)[0]
            if module == "openseespy.opensees":
                aggregate["hasOpenSeesImport"] = True
                for alias in node.names:
                    opensees_aliases.add(alias.asname or alias.name)
            if root in _BLOCKED_IMPORT_ROOTS:
                code = "SUBPROCESS" if root == "subprocess" else "NETWORK" if root in {"socket", "requests", "urllib"} else "CTYPES"
                safety_findings.append(
                    {"path": relative, "line": node.lineno, "code": code, "severity": "ERROR"}
                )
            local = _local_module_target(workspace, path, module)
            if local is not None:
                target = workspace_relative_path(workspace, local)
                dependencies.append(
                    {
                        "source": relative,
                        "reference": module,
                        "target": str(Path(target).relative_to(Path(relative).parent)),
                        "type": "PYTHON_IMPORT",
                        "role": "PYTHON_MODULE",
                    }
                )
                _scan_python_file(
                    workspace,
                    local,
                    visited=visited,
                    dependencies=dependencies,
                    safety_findings=safety_findings,
                    aggregate=aggregate,
                )
            elif module and _external_import(module):
                dependencies.append(
                    {
                        "source": relative,
                        "reference": module,
                        "target": None,
                        "type": "PYTHON_IMPORT",
                        "role": None,
                        "status": "EXTERNAL_PACKAGE",
                    }
                )
        elif isinstance(node, (ast.For, ast.While, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            aggregate["dynamicGeneration"] = True
        elif isinstance(node, ast.Call):
            owner, name = _call_name(node)
            if name in {"eval", "exec", "compile"} and owner is None:
                safety_findings.append(
                    {"path": relative, "line": node.lineno, "code": "DYNAMIC_EVAL", "severity": "ERROR"}
                )
            if owner == "os" and name == "system":
                safety_findings.append(
                    {"path": relative, "line": node.lineno, "code": "OS_SYSTEM", "severity": "ERROR"}
                )
            if owner == "os" and name == "popen":
                safety_findings.append(
                    {"path": relative, "line": node.lineno, "code": "OS_POPEN", "severity": "ERROR"}
                )
            if owner == "subprocess":
                safety_findings.append(
                    {"path": relative, "line": node.lineno, "code": "SUBPROCESS", "severity": "ERROR"}
                )

            is_opensees = owner in opensees_aliases
            if is_opensees and name is not None:
                api_signals[name] = api_signals.get(name, 0) + 1
                if name in _OPENSEES_BUILD_CALLS or name in _OPENSEES_ANALYSIS_CALLS:
                    aggregate["hasOpenSeesCalls"] = True
                if name == "model":
                    aggregate["hasModelCall"] = True
                elif name == "node":
                    tag = _literal_int(node.args[0] if node.args else None)
                    if tag is None:
                        aggregate["dynamicGeneration"] = True
                    else:
                        node_ids.add(tag)
                elif name == "element":
                    tag = _literal_int(node.args[1] if len(node.args) > 1 else None)
                    if tag is None:
                        aggregate["dynamicGeneration"] = True
                    else:
                        element_ids.add(tag)

            if name in _FILE_READ_CALLS:
                path_arg = node.args[0] if node.args else None
                literal = _literal_string(path_arg)
                if literal:
                    dependencies.append(
                        {
                            "source": relative,
                            "reference": literal,
                            "target": literal,
                            "type": "PYTHON_FILE_READ",
                            "role": "ENGINEERING_DATA",
                        }
                    )


def inspect_opensees_python(workspace: Path, raw_path: str) -> dict[str, Any]:
    path = resolve_workspace_file(workspace, raw_path)
    if path.suffix.lower() != ".py":
        raise FemCoreError(
            "UNSUPPORTED_MODEL_FORMAT",
            "OpenSees Python inspection requires a .py entrypoint",
            details={"suffix": path.suffix.lower()},
        )

    dependencies: list[dict[str, Any]] = []
    safety_findings: list[dict[str, Any]] = []
    aggregate: dict[str, Any] = {
        "hasOpenSeesImport": False,
        "hasOpenSeesCalls": False,
        "hasModelCall": False,
        "dynamicGeneration": False,
    }
    _scan_python_file(
        workspace.resolve(),
        path,
        visited=set(),
        dependencies=dependencies,
        safety_findings=safety_findings,
        aggregate=aggregate,
    )
    bundle = discover_bundle(workspace.resolve(), path, dependencies)
    if bundle["integrity"] == "BLOCKED":
        safety_findings.append(
            {
                "path": workspace_relative_path(workspace, path),
                "line": 0,
                "code": "BUNDLE_OUTSIDE_WORKSPACE",
                "severity": "ERROR",
            }
        )

    if safety_findings:
        classification = "UNSAFE"
        eligibility = "REJECTED"
    elif aggregate["hasOpenSeesImport"] and aggregate["hasModelCall"] and aggregate["hasOpenSeesCalls"]:
        classification = "MODEL_CONFIRMED"
        eligibility = "REQUIRES_BUILD_INSPECTION"
    elif aggregate["hasOpenSeesImport"] or aggregate["hasOpenSeesCalls"]:
        classification = "MODEL_LIKELY"
        eligibility = "REQUIRES_BUILD_INSPECTION"
    else:
        classification = "NOT_OPENSEES_MODEL"
        eligibility = "INCOMPLETE"

    dynamic = bool(aggregate["dynamicGeneration"])
    node_ids: set[int] = aggregate.get("nodeIds", set())
    element_ids: set[int] = aggregate.get("elementIds", set())
    source_content = path.read_bytes()
    return {
        "schemaVersion": "1.0",
        "kind": "opensees_python_model_inspection",
        "inspectionLevel": "STATIC_PYTHON_AST_V1",
        "format": "OPENSEES_PYTHON",
        "classification": classification,
        "executionEligibility": eligibility,
        "source": {
            "path": workspace_relative_path(workspace, path),
            "fileName": path.name,
            "suffix": ".py",
            "sha256": sha256(source_content).hexdigest(),
            "sizeBytes": len(source_content),
            "encoding": "utf-8",
        },
        "apiSignals": [
            {"name": name, "count": count}
            for name, count in sorted(dict(aggregate.get("apiSignals", {})).items())
        ],
        "staticTopology": {
            "nodeCount": None if dynamic else len(node_ids),
            "elementCount": None if dynamic else len(element_ids),
            "nodeTags": [] if dynamic else sorted(node_ids),
            "elementTags": [] if dynamic else sorted(element_ids),
            "basis": "UNKNOWN_UNTIL_BUILD_INSPECTION" if dynamic else "LITERAL_AST_CALLS",
        },
        "dynamicGeneration": dynamic,
        "safetyFindings": safety_findings,
        "bundle": bundle,
        "warnings": [
            "STATIC_PYTHON_FACTS_ARE_NOT_REALIZED_SOLVER_TOPOLOGY",
            "BUILD_INSPECTION_REQUIRED_BEFORE_EXECUTION",
        ],
    }
