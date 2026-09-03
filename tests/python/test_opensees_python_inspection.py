from pathlib import Path

from fem_core.opensees_python_inspection import inspect_opensees_python


def test_multifile_opensees_bundle_is_confirmed_and_dependencies_are_resolved(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_dir = project / "data"
    data_dir.mkdir(parents=True)
    (project / "materials.py").write_text(
        "import openseespy.opensees as ops\n"
        "def build_materials():\n"
        "    ops.uniaxialMaterial('Elastic', 1, 1.0e6)\n",
        encoding="utf-8",
    )
    (data_dir / "mass.csv").write_text("mass\n1000\n", encoding="utf-8")
    (project / "main.py").write_text(
        "import os\n"
        "import pandas as pd\n"
        "import openseespy.opensees as ops\n"
        "from materials import build_materials\n"
        "data_path = os.path.join('data', 'mass.csv')\n"
        "pd.read_csv('data/mass.csv')\n"
        "ops.model('basic', '-ndm', 1, '-ndf', 1)\n"
        "ops.node(1, 0.0)\n"
        "ops.node(2, 0.0)\n"
        "build_materials()\n"
        "ops.element('zeroLength', 1, 1, 2, '-mat', 1, '-dir', 1)\n",
        encoding="utf-8",
    )

    report = inspect_opensees_python(tmp_path, "project/main.py")

    assert report["classification"] == "MODEL_CONFIRMED"
    assert report["executionEligibility"] in {"STATICALLY_ELIGIBLE", "REQUIRES_BUILD_INSPECTION"}
    assert report["staticTopology"]["nodeCount"] == 2
    assert report["staticTopology"]["elementCount"] == 1
    assert report["safetyFindings"] == []
    bundle_paths = {item["path"] for item in report["bundle"]["files"]}
    assert {"project/main.py", "project/materials.py", "project/data/mass.csv"} <= bundle_paths
    assert len(report["bundle"]["bundleFingerprint"]) == 64


def test_loop_generated_topology_is_not_invented(tmp_path: Path) -> None:
    model = tmp_path / "dynamic.py"
    model.write_text(
        "import openseespy.opensees as ops\n"
        "ops.model('basic', '-ndm', 1, '-ndf', 1)\n"
        "for i in range(10):\n"
        "    ops.node(i + 1, float(i))\n"
        "ops.element('zeroLength', 1, 1, 2, '-mat', 1, '-dir', 1)\n",
        encoding="utf-8",
    )

    report = inspect_opensees_python(tmp_path, "dynamic.py")

    assert report["classification"] == "MODEL_CONFIRMED"
    assert report["dynamicGeneration"] is True
    assert report["staticTopology"]["nodeCount"] is None
    assert report["executionEligibility"] == "REQUIRES_BUILD_INSPECTION"


def test_dangerous_python_side_effects_are_rejected(tmp_path: Path) -> None:
    model = tmp_path / "unsafe.py"
    model.write_text(
        "import os\n"
        "import subprocess\n"
        "import openseespy.opensees as ops\n"
        "ops.model('basic', '-ndm', 1, '-ndf', 1)\n"
        "ops.node(1, 0.0)\n"
        "ops.node(2, 0.0)\n"
        "ops.element('zeroLength', 1, 1, 2, '-mat', 1, '-dir', 1)\n"
        "os.system('echo unsafe')\n"
        "subprocess.run(['echo', 'unsafe'])\n"
        "eval('1 + 1')\n",
        encoding="utf-8",
    )

    report = inspect_opensees_python(tmp_path, "unsafe.py")

    assert report["classification"] == "UNSAFE"
    assert report["executionEligibility"] == "REJECTED"
    codes = {finding["code"] for finding in report["safetyFindings"]}
    assert {"OS_SYSTEM", "SUBPROCESS", "DYNAMIC_EVAL"} <= codes


def test_literal_file_reference_outside_workspace_is_blocked(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    model = workspace / "main.py"
    model.write_text(
        "import openseespy.opensees as ops\n"
        "ops.model('basic', '-ndm', 1, '-ndf', 1)\n"
        "ops.node(1, 0.0)\n"
        "ops.node(2, 0.0)\n"
        "ops.element('zeroLength', 1, 1, 2, '-mat', 1, '-dir', 1)\n"
        "open('../outside.csv').read()\n",
        encoding="utf-8",
    )
    (tmp_path / "outside.csv").write_text("x\n1\n", encoding="utf-8")

    report = inspect_opensees_python(workspace, "main.py")

    assert report["executionEligibility"] == "REJECTED"
    assert report["bundle"]["integrity"] == "BLOCKED"
