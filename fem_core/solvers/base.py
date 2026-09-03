from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class SolverAdapter(ABC):
    """Deterministic boundary between FEMagent tools and a concrete FEM solver."""

    name: str

    @abstractmethod
    def status(self) -> dict[str, Any]:
        """Report whether the backend runtime is installed without running an analysis."""

    @abstractmethod
    def preflight(
        self,
        workspace: Path,
        *,
        model_path: str,
        load_path: str | None = None,
    ) -> dict[str, Any]:
        """Validate a model and optional load; concrete adapters enforce required inputs."""

    @abstractmethod
    def run(
        self,
        workspace: Path,
        *,
        model_path: str,
        load_path: str | None = None,
    ) -> dict[str, Any]:
        """Execute the solver; concrete adapters may reject a missing load for their model contract."""
