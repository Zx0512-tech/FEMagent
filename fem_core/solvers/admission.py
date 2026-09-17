from __future__ import annotations

from typing import Any

from fem_core.errors import FemCoreError
from fem_core.solvers.capability import get_solver_capability


def admit_analysis_execution(
    *,
    solver: str,
    profile: str,
    requested_quantities: list[str] | None = None,
) -> dict[str, Any]:
    """Check solver capability before entering preflight/run execution."""

    try:
        capability = get_solver_capability(solver)
    except KeyError as exc:
        raise FemCoreError(
            "SOLVER_CAPABILITY_UNAVAILABLE",
            "No capability contract exists for solver",
            details={"solver": solver},
        ) from exc

    if profile not in capability.profiles:
        raise FemCoreError(
            "SOLVER_PROFILE_UNSUPPORTED",
            "Solver does not support requested analysis profile",
            details={"solver": capability.solver, "profile": profile},
        )

    quantities = requested_quantities or []
    unsupported = sorted(set(quantities) - capability.quantities)
    if unsupported:
        raise FemCoreError(
            "SOLVER_RESULT_UNSUPPORTED",
            "Solver does not support requested result quantities",
            details={"solver": capability.solver, "unsupported": unsupported},
        )

    return {
        "status": "ADMITTED",
        "solver": capability.solver,
        "profile": profile,
        "requestedQuantities": quantities,
    }


__all__ = ["admit_analysis_execution"]
