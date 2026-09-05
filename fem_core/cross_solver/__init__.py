"""Deterministic cross-solver validation primitives."""

from .api import validate_cross_solver
from .validation import compare_role_evidence_reports

__all__ = ["compare_role_evidence_reports", "validate_cross_solver"]
