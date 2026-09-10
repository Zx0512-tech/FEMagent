from __future__ import annotations

from typing import Any

from fem_core.errors import FemCoreError

OPENSEES_STATIC_V1 = "OPENSEES_FRAME_2D_LINEAR_STATIC_V1"
OPENSEES_STATIC_V2 = "OPENSEES_FRAME_2D_LINEAR_STATIC_V2"
OPENSEES_MODAL_V2 = "OPENSEES_FRAME_2D_MODAL_V2"
OPENSEES_TRANSIENT_NODAL_V2 = "OPENSEES_FRAME_2D_TRANSIENT_NODAL_FORCE_V2"
OPENSEES_TRANSIENT_BASE_V2 = "OPENSEES_FRAME_2D_TRANSIENT_UNIFORM_BASE_V2"


def select_opensees_analysis_profile(spec: dict[str, Any]) -> str:
    version = spec.get("schemaVersion")
    analysis_type = spec.get("analysisType")

    if version == "1.0" and analysis_type == "LINEAR_STATIC":
        return OPENSEES_STATIC_V1
    if version == "2.0" and analysis_type == "LINEAR_STATIC":
        return OPENSEES_STATIC_V2
    if version == "2.0" and analysis_type == "MODAL":
        return OPENSEES_MODAL_V2
    if version == "2.0" and analysis_type == "TRANSIENT":
        definition = spec.get("definition")
        if isinstance(definition, dict):
            excitation = definition.get("excitation")
            if isinstance(excitation, dict):
                excitation_type = excitation.get("type")
                if excitation_type == "NODAL_TIME_HISTORY":
                    return OPENSEES_TRANSIENT_NODAL_V2
                if excitation_type == "UNIFORM_BASE_EXCITATION":
                    return OPENSEES_TRANSIENT_BASE_V2

    raise FemCoreError(
        "ANALYSIS_READINESS_UNSUPPORTED_PROFILE",
        "Unsupported OpenSees analysis profile",
        details={"schemaVersion": version, "analysisType": analysis_type},
    )


__all__ = [
    "OPENSEES_MODAL_V2",
    "OPENSEES_STATIC_V1",
    "OPENSEES_STATIC_V2",
    "OPENSEES_TRANSIENT_BASE_V2",
    "OPENSEES_TRANSIENT_NODAL_V2",
    "select_opensees_analysis_profile",
]
