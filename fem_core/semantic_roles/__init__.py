"""Deterministic engineering semantic-role resolution."""

from .api import inspect_semantic_roles, resolve_semantic_role
from .manifest import load_semantic_manifest

__all__ = [
    "inspect_semantic_roles",
    "load_semantic_manifest",
    "resolve_semantic_role",
]
