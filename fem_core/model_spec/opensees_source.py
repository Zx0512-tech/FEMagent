from __future__ import annotations

from typing import Any

from fem_core.errors import FemCoreError

GEOM_TRANSF_TAG = 1


def format_opensees_number(value: Any) -> str:
    number = float(value)
    if number == 0.0:
        return "0.0"
    return repr(number)


def _lookup_by_id(
    items: list[dict[str, Any]],
    identifier: int,
    *,
    namespace: str,
) -> dict[str, Any]:
    for item in items:
        if item["id"] == identifier:
            return item
    raise FemCoreError(
        "OPENSEES_RENDER_INTERNAL_INVARIANT",
        f"Validated ModelSpec lost referenced {namespace} {identifier}",
        details={"namespace": namespace, "id": identifier},
    )


def _constraint_flags(dofs: list[str]) -> tuple[int, int, int]:
    selected = set(dofs)
    return (
        1 if "UX" in selected else 0,
        1 if "UY" in selected else 0,
        1 if "RZ" in selected else 0,
    )


def build_opensees_frame_2d_model_source(spec: dict[str, Any]) -> str:
    lines = [
        "import openseespy.opensees as ops",
        "",
        "ops.wipe()",
        'ops.model("basic", "-ndm", 2, "-ndf", 3)',
        "",
    ]

    for node in sorted(spec["nodes"], key=lambda item: item["id"]):
        lines.append(
            f"ops.node({node['id']}, {format_opensees_number(node['x'])}, "
            f"{format_opensees_number(node['y'])})"
        )

    if spec["constraints"]:
        lines.append("")
        for constraint in sorted(spec["constraints"], key=lambda item: item["nodeId"]):
            ux, uy, rz = _constraint_flags(constraint["dofs"])
            lines.append(f"ops.fix({constraint['nodeId']}, {ux}, {uy}, {rz})")

    if spec["nodalMasses"]:
        lines.append("")
        for mass in sorted(spec["nodalMasses"], key=lambda item: item["nodeId"]):
            lines.append(
                "ops.mass("
                f"{mass['nodeId']}, {format_opensees_number(mass['mUX'])}, "
                f"{format_opensees_number(mass['mUY'])}, 0.0)"
            )

    lines.extend(["", f'ops.geomTransf("Linear", {GEOM_TRANSF_TAG})', ""])

    materials = list(spec["materials"])
    sections = list(spec["sections"])
    for element in sorted(spec["elements"], key=lambda item: item["id"]):
        material = _lookup_by_id(materials, element["materialId"], namespace="material")
        section = _lookup_by_id(sections, element["sectionId"], namespace="section")
        lines.append(
            'ops.element("elasticBeamColumn", '
            f"{element['id']}, {element['nodeI']}, {element['nodeJ']}, "
            f"{format_opensees_number(section['area'])}, "
            f"{format_opensees_number(material['youngsModulus'])}, "
            f"{format_opensees_number(section['iz'])}, {GEOM_TRANSF_TAG})"
        )

    return "\n".join(lines) + "\n"


__all__ = [
    "GEOM_TRANSF_TAG",
    "build_opensees_frame_2d_model_source",
    "format_opensees_number",
]
