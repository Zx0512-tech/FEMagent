from __future__ import annotations

import platform
import sys
from typing import Any

from fem_core import __version__


def build_health_report() -> dict[str, Any]:
    """Return bootstrap runtime health without probing external solvers."""
    return {
        "status": "ok",
        "core": "fem_core",
        "coreVersion": __version__,
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "platform": sys.platform,
        "solvers": {
            "ansys": "not_checked",
            "opensees": "not_checked",
        },
    }
