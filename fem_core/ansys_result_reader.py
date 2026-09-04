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
    except (AttributeError, IndexError, KeyError, ValueError):
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
        for quantity in ("DISPLACEMENT", "VELOCITY", "ACCELERATION", "REACTION_FORCE")
        if _available_quantity(result, quantity)
    ]
    return {
        "schemaVersion": "1.0",
        "kind": "ansys_binary_result",
        "format": "MAPDL_BINARY_RESULT",
        "suffix": path.suffix.lower(),
        "resultSetCount": nsets,
        "nodeCount": node_count,
        "dofLabels": dofs,
        "quantities": quantities,
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
