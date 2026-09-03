from __future__ import annotations

from fem_core.errors import FemCoreError
from fem_core.solvers.base import SolverAdapter


def get_solver_adapter(name: str) -> SolverAdapter:
    normalized = str(name).strip().lower()
    if normalized in {"opensees", "openseespy"}:
        from fem_core.solvers.opensees_python import OpenSeesBundleAdapter

        return OpenSeesBundleAdapter()
    raise FemCoreError(
        "UNSUPPORTED_SOLVER",
        "The requested FEM solver adapter is not available",
        details={"solver": name, "supported": ["opensees"]},
    )
