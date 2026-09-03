import openseespy.opensees as ops


def build_materials() -> None:
    ops.uniaxialMaterial("Elastic", 1, 1000.0)
