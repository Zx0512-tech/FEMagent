from __future__ import annotations

from types import NoneType, UnionType
from typing import get_args, get_type_hints

from fem_core.solvers.base import SolverAdapter


def _allows_none(annotation: object) -> bool:
    return isinstance(annotation, UnionType) and NoneType in get_args(annotation)


def test_solver_adapter_load_path_contract_allows_none() -> None:
    preflight_hints = get_type_hints(SolverAdapter.preflight)
    run_hints = get_type_hints(SolverAdapter.run)

    assert _allows_none(preflight_hints["load_path"])
    assert _allows_none(run_hints["load_path"])
