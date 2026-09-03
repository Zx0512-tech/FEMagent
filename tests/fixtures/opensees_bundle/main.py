import openseespy.opensees as ops

from materials import build_materials

ops.model("basic", "-ndm", 1, "-ndf", 1)
ops.node(1, 0.0)
ops.node(2, 0.0)
ops.fix(1, 1)
ops.mass(2, 1.0)
build_materials()
ops.element("zeroLength", 1, 1, 2, "-mat", 1, "-dir", 1)
ops.timeSeries("Linear", 1)
ops.pattern("Plain", 1, 1)
ops.load(2, 1.0)
ops.constraints("Plain")
ops.numberer("Plain")
ops.system("BandGeneral")
ops.algorithm("Linear")
ops.integrator("LoadControl", 1.0)
ops.analysis("Static")
ops.analyze(1)
