from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from fem_core.errors import FemCoreError

_ANSYS_BINARY_SUFFIXES = {".rst", ".rth", ".rfl", ".rmg"}
_QUANTITY_TO_SOLUTION_TYPE = {
    "DISPLACEMENT": "NSL",
    "VELOCITY": "VEL",
    "ACCELERATION": "ACC",
}
_COMPONENT_ALIASES = {
    "X": "UX",
    "UX": "UX",
    "U1": "UX",
    "1": "UX",
    "Y": "UY",
    "UY": "UY",
    "U2": "UY",
    "2": "UY",
    "Z": "UZ",
    "UZ": "UZ",
    "U3": "UZ",
    "3": "UZ",
}
_DOF_TO_AXIS = {"UX": "X", "UY": "Y", "UZ": "Z"}
_STRESS_COMPONENT_INDEX = {"SX": 0, "SY": 1, "SZ": 2, "SXY": 3, "SYZ": 4, "SXZ": 5}
_PRINCIPAL_STRESS_COMPONENT_INDEX = {"S1": 0, "S2": 1, "S3": 2, "SINT": 3, "SEQV": 4}


def _reader_module():
    try:
        from ansys.mapdl import reader as pymapdl_reader
    except ImportError as exc:  # pragma: no cover - exercised when optional extra is absent
        raise FemCoreError(
            "ANSYS_RESULT_READER_UNAVAILABLE",
            "ANSYS binary result support requires the optional ansys-results dependency",
        ) from exc
    return pymapdl_reader


def _open_result(path: Path):
    resolved = path.resolve()
    if resolved.suffix.lower() not in _ANSYS_BINARY_SUFFIXES:
        raise FemCoreError(
            "UNSUPPORTED_ANSYS_RESULT_FORMAT",
            "ANSYS Result Intelligence supports MAPDL binary result files only",
            details={"suffix": resolved.suffix.lower()},
        )
    if not resolved.is_file():
        raise FemCoreError(
            "ANSYS_BINARY_RESULT_NOT_FOUND",
            "Recorded ANSYS binary result file does not exist",
            details={"path": str(resolved)},
        )
    try:
        return _reader_module().read_binary(str(resolved), parse_vtk=False)
    except FemCoreError:
        raise
    except Exception as exc:
        raise FemCoreError(
            "INVALID_ANSYS_BINARY_RESULT",
            "Unable to read the recorded ANSYS MAPDL binary result file",
            details={"path": str(resolved), "reason": str(exc)},
        ) from exc


def _float_values(values: Any, *, label: str) -> list[float]:
    output: list[float] = []
    for index, raw in enumerate(values):
        value = float(raw)
        if not math.isfinite(value):
            raise FemCoreError(
                "INVALID_ANSYS_RESULT_SERIES",
                "ANSYS result series contains a non-finite value",
                details={"series": label, "index": index},
            )
        output.append(value)
    return output


def _result_dofs(result: Any) -> list[str]:
    if int(result.nsets) <= 0:
        return []
    try:
        return [str(value).strip().upper() for value in result.result_dof(0)]
    except Exception as exc:
        raise FemCoreError(
            "INVALID_ANSYS_BINARY_RESULT",
            "Unable to read ANSYS result DOF labels",
            details={"reason": str(exc)},
        ) from exc


def _available_quantity(result: Any, quantity: str) -> bool:
    if int(result.nsets) <= 0:
        return False
    try:
        if quantity == "DISPLACEMENT":
            return bool(result.available_results["NSL"])
        if quantity == "VELOCITY":
            return bool(result.available_results["VSL"])
        if quantity == "ACCELERATION":
            return bool(result.available_results["ASL"])
        if quantity == "REACTION_FORCE":
            result.nodal_reaction_forces(0)
            return True
        if quantity == "STRESS":
            result.nodal_stress(0)
            return True
        if quantity == "PRINCIPAL_STRESS":
            result.principal_nodal_stress(0)
            return True
    except (AttributeError, IndexError, KeyError, RuntimeError, ValueError):
        return False
    return False


def describe_ansys_binary_result(path: Path) -> dict[str, Any]:
    result = _open_result(path)
    nsets = int(result.nsets)
    times = _float_values(result.time_values, label="abscissa") if nsets else []
    dofs = _result_dofs(result)
    try:
        node_count = len(result.mesh.nnum)
    except Exception as exc:
        raise FemCoreError(
            "INVALID_ANSYS_BINARY_RESULT",
            "Unable to read ANSYS result mesh node identifiers",
            details={"reason": str(exc)},
        ) from exc

    quantities = [
        quantity
        for quantity in (
            "DISPLACEMENT",
            "VELOCITY",
            "ACCELERATION",
            "REACTION_FORCE",
            "STRESS",
            "PRINCIPAL_STRESS",
        )
        if _available_quantity(result, quantity)
    ]
    structural_capabilities: list[dict[str, Any]] = []
    if "STRESS" in quantities:
        structural_capabilities.append(
            {
                "quantity": "STRESS",
                "targetType": "NODE",
                "components": list(_STRESS_COMPONENT_INDEX),
                "stressLocation": "NODAL_AVERAGED",
                "referenceFrame": "GLOBAL",
            }
        )
    if "PRINCIPAL_STRESS" in quantities:
        structural_capabilities.append(
            {
                "quantity": "PRINCIPAL_STRESS",
                "targetType": "NODE",
                "components": list(_PRINCIPAL_STRESS_COMPONENT_INDEX),
                "stressLocation": "NODAL_AVERAGED",
                "referenceFrame": "GLOBAL",
            }
        )
    return {
        "schemaVersion": "1.0",
        "kind": "ansys_binary_result",
        "format": "MAPDL_BINARY_RESULT",
        "suffix": path.suffix.lower(),
        "resultSetCount": nsets,
        "nodeCount": node_count,
        "dofLabels": dofs,
        "quantities": quantities,
        "structuralCapabilities": structural_capabilities,
        "abscissa": {
            "semantic": "SOLVER_NATIVE_RESULT_ABSCISSA",
            "unit": None,
            "sampleCount": len(times),
            "start": times[0] if times else None,
            "end": times[-1] if times else None,
        },
    }


def _normalize_component(component: str) -> tuple[str, str]:
    normalized = _COMPONENT_ALIASES.get(str(component).strip().upper())
    if normalized is None:
        raise FemCoreError(
            "RESULT_SERIES_UNAVAILABLE",
            "Requested ANSYS nodal component is not supported by PR9",
            details={"component": component},
        )
    return _DOF_TO_AXIS[normalized], normalized


def _query_standard_nodal(
    result: Any,
    *,
    quantity: str,
    node_id: int,
    source_dof: str,
) -> tuple[list[float], list[float]]:
    solution_type = _QUANTITY_TO_SOLUTION_TYPE[quantity]
    try:
        nnum, data = result.nodal_time_history(solution_type)
        dofs = [str(value).strip().upper() for value in result.result_dof(0)]
    except (AttributeError, IndexError, KeyError, ValueError) as exc:
        raise FemCoreError(
            "RESULT_SERIES_UNAVAILABLE",
            "The ANSYS binary result does not contain the requested nodal result type",
            details={"quantity": quantity, "reason": str(exc)},
        ) from exc

    node_indices = [index for index, value in enumerate(nnum) if int(value) == node_id]
    if not node_indices or source_dof not in dofs:
        raise FemCoreError(
            "RESULT_SERIES_UNAVAILABLE",
            "The ANSYS binary result does not contain the requested node/component series",
            details={"nodeId": node_id, "dof": source_dof},
        )
    node_index = node_indices[0]
    dof_index = dofs.index(source_dof)
    values = _float_values(
        (data[result_index, node_index, dof_index] for result_index in range(int(result.nsets))),
        label=f"{quantity}:{node_id}:{source_dof}",
    )
    return _float_values(result.time_values, label="abscissa"), values


def _query_reaction(
    result: Any,
    *,
    node_id: int,
    source_dof: str,
) -> tuple[list[float], list[float]]:
    values: list[float] = []
    for rnum in range(int(result.nsets)):
        try:
            reaction, nodes, dof_indices = result.nodal_reaction_forces(rnum)
            dof_labels = [str(value).strip().upper() for value in result.result_dof(rnum)]
        except (AttributeError, IndexError, KeyError, ValueError) as exc:
            raise FemCoreError(
                "RESULT_SERIES_UNAVAILABLE",
                "The ANSYS binary result does not contain a complete reaction-force series",
                details={"resultSet": rnum, "reason": str(exc)},
            ) from exc
        matches: list[float] = []
        for raw_force, raw_node, raw_dof_index in zip(reaction, nodes, dof_indices):
            index = int(raw_dof_index) - 1
            if (
                0 <= index < len(dof_labels)
                and int(raw_node) == node_id
                and dof_labels[index] == source_dof
            ):
                matches.append(float(raw_force))
        if len(matches) != 1 or not math.isfinite(matches[0]):
            raise FemCoreError(
                "RESULT_SERIES_UNAVAILABLE",
                "The requested ANSYS nodal reaction is not uniquely available for every result set",
                details={"resultSet": rnum, "nodeId": node_id, "dof": source_dof},
            )
        values.append(matches[0])
    return _float_values(result.time_values, label="abscissa"), values


def query_ansys_nodal_result(
    path: Path,
    *,
    quantity: str,
    node_id: int,
    component: str,
) -> dict[str, Any]:
    normalized_quantity = str(quantity).strip().upper()
    if normalized_quantity not in {*_QUANTITY_TO_SOLUTION_TYPE, "REACTION_FORCE"}:
        raise FemCoreError(
            "RESULT_SERIES_UNAVAILABLE",
            "Requested ANSYS result quantity is not supported by PR9",
            details={"quantity": quantity},
        )
    if not isinstance(node_id, int) or isinstance(node_id, bool) or node_id <= 0:
        raise FemCoreError("INVALID_RESULT_QUERY", "ANSYS result query node id must be positive")
    axis, source_dof = _normalize_component(component)
    result = _open_result(path)
    if normalized_quantity == "REACTION_FORCE":
        abscissa, values = _query_reaction(result, node_id=node_id, source_dof=source_dof)
    else:
        abscissa, values = _query_standard_nodal(
            result,
            quantity=normalized_quantity,
            node_id=node_id,
            source_dof=source_dof,
        )
    if len(abscissa) != len(values):
        raise FemCoreError(
            "INVALID_ANSYS_RESULT_SERIES",
            "ANSYS result abscissa and value counts do not match",
            details={"abscissaCount": len(abscissa), "valueCount": len(values)},
        )
    return {
        "quantity": normalized_quantity,
        "target": {"type": "NODE", "id": node_id},
        "component": axis,
        "sourceDof": source_dof,
        "unit": None,
        "referenceFrame": "SOLVER_NATIVE",
        "abscissaSemantic": "SOLVER_NATIVE_RESULT_ABSCISSA",
        "abscissaUnit": None,
        "abscissaValues": abscissa,
        "values": values,
    }


def _query_nodal_matrix_series(
    result: Any,
    *,
    node_id: int,
    method_name: str,
    component_index: int,
    label: str,
) -> tuple[list[float], list[float]]:
    values: list[float] = []
    for rnum in range(int(result.nsets)):
        try:
            nnum, data = getattr(result, method_name)(rnum)
        except (AttributeError, IndexError, KeyError, RuntimeError, ValueError) as exc:
            raise FemCoreError(
                "RESULT_SERIES_UNAVAILABLE",
                "The ANSYS binary result does not contain a complete structural response series",
                details={"resultSet": rnum, "quantity": label, "reason": str(exc)},
            ) from exc
        matches = [index for index, raw_node in enumerate(nnum) if int(raw_node) == node_id]
        if len(matches) != 1:
            raise FemCoreError(
                "RESULT_SERIES_UNAVAILABLE",
                "The requested ANSYS structural response node is not uniquely available",
                details={"resultSet": rnum, "nodeId": node_id, "quantity": label},
            )
        row = data[matches[0]]
        if component_index >= len(row):
            raise FemCoreError(
                "RESULT_SERIES_UNAVAILABLE",
                "The requested ANSYS structural response component is unavailable",
                details={"resultSet": rnum, "nodeId": node_id, "quantity": label},
            )
        value = float(row[component_index])
        if not math.isfinite(value):
            raise FemCoreError(
                "RESULT_SERIES_UNAVAILABLE",
                "The requested ANSYS structural response is non-finite",
                details={"resultSet": rnum, "nodeId": node_id, "quantity": label},
            )
        values.append(value)
    return _float_values(result.time_values, label="abscissa"), values


def query_ansys_structural_result(
    path: Path,
    *,
    quantity: str,
    target: dict[str, Any],
    component: str,
    location: str | None = None,
) -> dict[str, Any]:
    normalized_quantity = str(quantity).strip().upper()
    target_type = str(target.get("type") or "").strip().upper() if isinstance(target, dict) else ""
    target_id = target.get("id") if isinstance(target, dict) else None
    normalized_component = str(component).strip().upper()
    if target_type != "NODE" or not isinstance(target_id, int) or isinstance(target_id, bool) or target_id <= 0:
        raise FemCoreError(
            "RESULT_SERIES_UNAVAILABLE",
            "PR15 ANSYS structural stress queries currently require a positive NODE target",
            details={"target": target},
        )
    if location is not None:
        raise FemCoreError(
            "RESULT_SERIES_UNAVAILABLE",
            "Nodal averaged ANSYS stress does not accept an element location selector",
            details={"location": location},
        )

    if normalized_quantity == "STRESS":
        component_index = _STRESS_COMPONENT_INDEX.get(normalized_component)
        method_name = "nodal_stress"
    elif normalized_quantity == "PRINCIPAL_STRESS":
        component_index = _PRINCIPAL_STRESS_COMPONENT_INDEX.get(normalized_component)
        method_name = "principal_nodal_stress"
    else:
        raise FemCoreError(
            "RESULT_SERIES_UNAVAILABLE",
            "Requested ANSYS structural response quantity is not supported by PR15",
            details={"quantity": quantity},
        )
    if component_index is None:
        raise FemCoreError(
            "RESULT_SERIES_UNAVAILABLE",
            "Requested ANSYS structural response component is not supported",
            details={"quantity": normalized_quantity, "component": component},
        )

    result = _open_result(path)
    abscissa, values = _query_nodal_matrix_series(
        result,
        node_id=target_id,
        method_name=method_name,
        component_index=component_index,
        label=f"{normalized_quantity}:{normalized_component}",
    )
    return {
        "quantity": normalized_quantity,
        "target": {"type": "NODE", "id": target_id},
        "component": normalized_component,
        "stressLocation": "NODAL_AVERAGED",
        "unit": None,
        "referenceFrame": "GLOBAL",
        "abscissaSemantic": "SOLVER_NATIVE_RESULT_ABSCISSA",
        "abscissaUnit": None,
        "abscissaValues": abscissa,
        "values": values,
    }
