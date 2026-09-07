from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

from fem_core.model_spec.validator import validate_engineering_model_spec

READINESS_SCHEMA = "FEMAGENT_MODEL_SPEC_READINESS_V1"
READINESS_PROFILE = "FRAME_2D_ELASTIC_READINESS_V1"
_REQUIRED_RANK = 3


def _compact_validation(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": validation["schema"],
        "status": validation["status"],
        "issues": validation["issues"],
    }


def _invalid_spec_result(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": READINESS_SCHEMA,
        "status": "INVALID_SPEC",
        "profile": READINESS_PROFILE,
        "modelSpecFingerprint": None,
        "validation": _compact_validation(validation),
        "checks": {
            "connectivity": {"status": "SKIPPED", "componentCount": 0, "components": []},
            "rigidBodyRestraint": {
                "status": "SKIPPED",
                "requiredRankPerComponent": _REQUIRED_RANK,
                "components": [],
            },
            "parallelConnectivity": {"status": "SKIPPED", "groups": []},
        },
        "issues": [
            {
                "severity": "ERROR",
                "code": "MODEL_READINESS_INVALID_SPEC",
                "path": "",
                "message": "Engineering readiness requires a PR21-valid ModelSpec",
            }
        ],
    }


def _connected_components(spec: dict[str, Any]) -> list[dict[str, Any]]:
    node_ids = sorted(node["id"] for node in spec["nodes"])
    adjacency = {node_id: set() for node_id in node_ids}
    element_by_pair: dict[tuple[int, int], list[int]] = {}
    for element in spec["elements"]:
        node_i = element["nodeI"]
        node_j = element["nodeJ"]
        adjacency[node_i].add(node_j)
        adjacency[node_j].add(node_i)
        pair = tuple(sorted((node_i, node_j)))
        element_by_pair.setdefault(pair, []).append(element["id"])

    components: list[dict[str, Any]] = []
    visited: set[int] = set()
    for start in node_ids:
        if start in visited:
            continue
        stack = [start]
        nodes: list[int] = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            nodes.append(current)
            for neighbor in sorted(adjacency[current], reverse=True):
                if neighbor not in visited:
                    stack.append(neighbor)
        nodes.sort()
        node_set = set(nodes)
        element_ids = sorted(
            element["id"]
            for element in spec["elements"]
            if element["nodeI"] in node_set and element["nodeJ"] in node_set
        )
        components.append({"nodeIds": nodes, "elementIds": element_ids})

    components.sort(key=lambda item: item["nodeIds"][0])
    return [
        {"index": index, "nodeIds": item["nodeIds"], "elementIds": item["elementIds"]}
        for index, item in enumerate(components)
    ]


def _decimal(value: int | float) -> Decimal:
    return Decimal(str(value))


def _fraction_free_rank(rows: list[list[Decimal]]) -> int:
    if not rows:
        return 0
    max_digits = max(
        (len(value.as_tuple().digits) for row in rows for value in row if value != 0),
        default=1,
    )
    matrix = [list(row) for row in rows]
    rank = 0
    with localcontext() as context:
        context.prec = max(64, max_digits * 8 + 32)
        for column in range(3):
            pivot_index = next(
                (index for index in range(rank, len(matrix)) if matrix[index][column] != 0),
                None,
            )
            if pivot_index is None:
                continue
            matrix[rank], matrix[pivot_index] = matrix[pivot_index], matrix[rank]
            pivot = matrix[rank][column]
            for row_index in range(rank + 1, len(matrix)):
                factor = matrix[row_index][column]
                if factor == 0:
                    continue
                for col_index in range(column, 3):
                    matrix[row_index][col_index] = (
                        matrix[row_index][col_index] * pivot
                        - matrix[rank][col_index] * factor
                    )
            rank += 1
            if rank == 3:
                break
    return rank


def _rigid_body_check(
    spec: dict[str, Any], components: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    coordinates = {
        node["id"]: (_decimal(node["x"]), _decimal(node["y"])) for node in spec["nodes"]
    }
    constraints = {item["nodeId"]: item["dofs"] for item in spec["constraints"]}
    results: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    for component in components:
        rows: list[list[Decimal]] = []
        for node_id in component["nodeIds"]:
            x, y = coordinates[node_id]
            for dof in constraints.get(node_id, []):
                if dof == "UX":
                    rows.append([Decimal(1), Decimal(0), -y])
                elif dof == "UY":
                    rows.append([Decimal(0), Decimal(1), x])
                elif dof == "RZ":
                    rows.append([Decimal(0), Decimal(0), Decimal(1)])
        rank = _fraction_free_rank(rows)
        deficiency = _REQUIRED_RANK - rank
        result = {
            "index": component["index"],
            "nodeIds": component["nodeIds"],
            "elementIds": component["elementIds"],
            "constraintRank": rank,
            "deficiency": deficiency,
        }
        results.append(result)
        if rank < _REQUIRED_RANK:
            issues.append(
                {
                    "severity": "ERROR",
                    "code": "MODEL_READINESS_RIGID_BODY_RESTRAINT_INSUFFICIENT",
                    "path": f"components[{component['index']}]",
                    "message": (
                        f"Component {component['index']} has planar rigid-body restraint "
                        f"rank {rank}; required rank is {_REQUIRED_RANK}"
                    ),
                }
            )

    return (
        {
            "status": "FAIL" if issues else "PASS",
            "requiredRankPerComponent": _REQUIRED_RANK,
            "components": results,
        },
        issues,
    )


def _parallel_connectivity(
    spec: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_pair: dict[tuple[int, int], list[int]] = {}
    for element in spec["elements"]:
        pair = tuple(sorted((element["nodeI"], element["nodeJ"])))
        by_pair.setdefault(pair, []).append(element["id"])

    groups = [
        {"nodeIds": [pair[0], pair[1]], "elementIds": sorted(element_ids)}
        for pair, element_ids in sorted(by_pair.items())
        if len(element_ids) > 1
    ]
    issues = [
        {
            "severity": "WARNING",
            "code": "MODEL_READINESS_PARALLEL_CONNECTIVITY",
            "path": f"parallelConnectivity[{index}]",
            "message": (
                f"Nodes {group['nodeIds'][0]} and {group['nodeIds'][1]} are connected by "
                f"multiple elements {group['elementIds']}"
            ),
        }
        for index, group in enumerate(groups)
    ]
    return ({"status": "WARN" if groups else "PASS", "groups": groups}, issues)


def evaluate_engineering_model_readiness(spec: dict[str, Any]) -> dict[str, Any]:
    validation = validate_engineering_model_spec(spec)
    if validation["status"] == "INVALID":
        return _invalid_spec_result(validation)

    normalized = validation["normalizedSpec"]
    components = _connected_components(normalized)
    connectivity_issues: list[dict[str, Any]] = []
    if len(components) > 1:
        connectivity_issues.append(
            {
                "severity": "WARNING",
                "code": "MODEL_READINESS_DISCONNECTED_COMPONENTS",
                "path": "components",
                "message": f"Model contains {len(components)} disconnected components",
            }
        )
    connectivity = {
        "status": "WARN" if connectivity_issues else "PASS",
        "componentCount": len(components),
        "components": components,
    }

    rigid_body, rigid_body_issues = _rigid_body_check(normalized, components)
    parallel, parallel_issues = _parallel_connectivity(normalized)
    issues = connectivity_issues + rigid_body_issues + parallel_issues

    return {
        "schema": READINESS_SCHEMA,
        "status": "NOT_READY" if rigid_body_issues else "READY",
        "profile": READINESS_PROFILE,
        "modelSpecFingerprint": validation["modelSpecFingerprint"],
        "validation": _compact_validation(validation),
        "checks": {
            "connectivity": connectivity,
            "rigidBodyRestraint": rigid_body,
            "parallelConnectivity": parallel,
        },
        "issues": issues,
    }
