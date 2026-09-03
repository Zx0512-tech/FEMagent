from __future__ import annotations

from pathlib import Path
from types import NoneType, UnionType
from typing import get_args, get_type_hints

import pytest

from fem_core.errors import FemCoreError
from fem_core.solvers.base import SolverAdapter
from fem_core.solvers.registry import get_solver_adapter


def _allows_none(annotation: object) -> bool:
    return isinstance(annotation, UnionType) and NoneType in get_args(annotation)


def test_solver_adapter_load_path_contract_allows_none() -> None:
    preflight_hints = get_type_hints(SolverAdapter.preflight)
    run_hints = get_type_hints(SolverAdapter.run)

    assert _allows_none(preflight_hints["load_path"])
    assert _allows_none(run_hints["load_path"])


def test_controlled_opensees_json_model_still_requires_external_load(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    model.write_text(
        Path("tests/fixtures/opensees_sdof.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    adapter = get_solver_adapter("opensees")

    for operation in (adapter.preflight, adapter.run):
        with pytest.raises(FemCoreError) as exc_info:
            operation(tmp_path, model_path="model.json", load_path=None)
        assert exc_info.value.code == "LOAD_REQUIRED"
