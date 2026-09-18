from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SolverCapability:
    """Declared solver support boundary used before execution."""

    solver: str
    profiles: frozenset[str]
    quantities: frozenset[str]


OPENSEES_CAPABILITY = SolverCapability(
    solver="OPENSEES",
    profiles=frozenset(
        {
            "OPENSEES_FRAME_2D_LINEAR_STATIC_V1",
            "OPENSEES_FRAME_2D_LINEAR_STATIC_V2",
            "OPENSEES_FRAME_2D_MODAL_V2",
            "OPENSEES_FRAME_2D_TRANSIENT_NODAL_FORCE_V2",
            "OPENSEES_FRAME_2D_TRANSIENT_UNIFORM_BASE_V2",
        }
    ),
    quantities=frozenset(
        {
            "DISPLACEMENT",
            "VELOCITY",
            "ACCELERATION",
            "RELATIVE_ACCELERATION",
            "REACTION_FORCE",
            "REACTION_MOMENT",
            "GENERALIZED_FORCE",
            "EIGENVALUE",
            "NATURAL_FREQUENCY",
            "PERIOD",
            "MODE_SHAPE",
        }
    ),
)


_SOLVER_CAPABILITIES = {
    OPENSEES_CAPABILITY.solver: OPENSEES_CAPABILITY,
}


def get_solver_capability(solver: str) -> SolverCapability:
    key = str(solver).strip().upper()
    if key not in _SOLVER_CAPABILITIES:
        raise KeyError(key)
    return _SOLVER_CAPABILITIES[key]


__all__ = ["SolverCapability", "OPENSEES_CAPABILITY", "get_solver_capability"]
