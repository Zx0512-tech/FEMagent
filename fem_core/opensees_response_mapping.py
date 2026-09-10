from __future__ import annotations

from typing import Any

from fem_core.errors import FemCoreError

NODE_DOF = {"X": 1, "Y": 2, "Z": 3}
ELASTIC_BEAM_2D_LOCAL_FORCE = {
    ("N", "END_I"): 0,
    ("VY", "END_I"): 1,
    ("MZ", "END_I"): 2,
    ("N", "END_J"): 3,
    ("VY", "END_J"): 4,
    ("MZ", "END_J"): 5,
}


def _unavailable(channel: dict[str, Any], *, element_type: str | None) -> FemCoreError:
    return FemCoreError(
        "STRUCTURAL_RESPONSE_MAPPING_UNAVAILABLE",
        "OpenSees response does not have a proven canonical mapping",
        details={
            "channelId": channel.get("channelId") or channel.get("requestId"),
            "quantity": channel.get("quantity"),
            "component": channel.get("component"),
            "location": channel.get("location"),
            "target": channel.get("target"),
            "elementType": element_type,
        },
    )


def resolve_opensees_response_access(
    channel: dict[str, Any],
    *,
    element_type: str | None = None,
) -> dict[str, Any]:
    target = channel.get("target")
    if not isinstance(target, dict):
        raise _unavailable(channel, element_type=element_type)

    quantity = channel.get("quantity")
    component = channel.get("component")
    target_type = target.get("type")

    if quantity == "DISPLACEMENT" and target_type == "NODE" and component in {"X", "Y"}:
        return {
            "access": "NODE_DISP",
            "dof": NODE_DOF[str(component)],
            "referenceFrame": "GLOBAL",
        }

    if quantity == "VELOCITY" and target_type == "NODE" and component in {"X", "Y"}:
        return {
            "access": "NODE_VEL",
            "dof": NODE_DOF[str(component)],
            "referenceFrame": "GLOBAL",
        }

    if (
        quantity in {"ACCELERATION", "RELATIVE_ACCELERATION"}
        and target_type == "NODE"
        and component in {"X", "Y"}
    ):
        return {
            "access": "NODE_ACCEL",
            "dof": NODE_DOF[str(component)],
            "referenceFrame": "GLOBAL",
        }

    if (
        quantity in {"REACTION_FORCE", "REACTION_MOMENT"}
        and target_type == "NODE"
        and component in NODE_DOF
    ):
        if quantity == "REACTION_FORCE" and component not in {"X", "Y"}:
            raise _unavailable(channel, element_type=element_type)
        if quantity == "REACTION_MOMENT" and component != "Z":
            raise _unavailable(channel, element_type=element_type)
        return {
            "access": "NODE_REACTION",
            "dof": NODE_DOF[str(component)],
            "referenceFrame": "GLOBAL",
        }

    if quantity == "GENERALIZED_FORCE" and target_type == "ELEMENT" and element_type == "ElasticBeam2d":
        key = (str(component), str(channel.get("location")))
        index = ELASTIC_BEAM_2D_LOCAL_FORCE.get(key)
        if index is not None:
            return {
                "access": "ELEMENT_LOCAL_FORCE",
                "response": "localForce",
                "index": index,
                "vectorLength": 6,
                "referenceFrame": "ELEMENT_LOCAL",
            }

    raise _unavailable(channel, element_type=element_type)


def derive_response_unit(channel: dict[str, Any], model_units: dict[str, str]) -> str:
    force = model_units["force"]
    length = model_units["length"]
    time = model_units["time"]
    quantity = channel.get("quantity")
    component = channel.get("component")

    if quantity == "DISPLACEMENT":
        return length
    if quantity == "VELOCITY":
        return f"{length}/{time}"
    if quantity in {"ACCELERATION", "RELATIVE_ACCELERATION"}:
        return f"{length}/{time}2"
    if quantity == "REACTION_FORCE":
        return force
    if quantity == "REACTION_MOMENT":
        return f"{force}*{length}"
    if quantity == "GENERALIZED_FORCE" and component in {"N", "VY"}:
        return force
    if quantity == "GENERALIZED_FORCE" and component == "MZ":
        return f"{force}*{length}"

    raise _unavailable(channel, element_type=None)


__all__ = [
    "ELASTIC_BEAM_2D_LOCAL_FORCE",
    "NODE_DOF",
    "derive_response_unit",
    "resolve_opensees_response_access",
]
