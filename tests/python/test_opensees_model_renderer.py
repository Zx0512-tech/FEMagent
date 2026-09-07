from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from fem_core.errors import FemCoreError
from fem_core.model_spec import opensees_renderer as renderer_module

render_opensees_frame_2d = renderer_module.render_opensees_frame_2d

FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def _load_spec() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _artifact_path(workspace: Path, report: dict[str, object], key: str) -> Path:
    artifacts = report["artifacts"]
    assert isinstance(artifacts, dict)
    value = artifacts[key]
    assert isinstance(value, str)
    return workspace / Path(value)


def _rendered_source(workspace: Path, report: dict[str, object]) -> str:
    return _artifact_path(workspace, report, "modelPath").read_text(encoding="utf-8")


def test_golden_portal_frame_renders_construction_only_opensees_script(tmp_path: Path) -> None:
    spec = _load_spec()

    report = render_opensees_frame_2d(tmp_path, spec)

    assert report["schema"] == "FEMAGENT_OPENSEES_RENDER_V1"
    assert report["status"] == "RENDERED"
    assert report["renderer"] == {"name": "OPENSEES_FRAME_2D_V1", "version": "1.0"}
    assert report["input"]["readinessProfile"] == "FRAME_2D_ELASTIC_READINESS_V1"
    assert report["mapping"] == {
        "nodeTagPolicy": "IDENTITY",
        "elementTagPolicy": "IDENTITY",
        "geomTransfTag": 1,
        "nodeCount": 4,
        "elementCount": 3,
    }
    assert report["renderId"].startswith("render_")
    assert len(report["renderId"]) == len("render_") + 16
    assert len(report["artifacts"]["modelSha256"]) == 64
    assert len(report["renderFingerprint"]) == 64

    model_path = _artifact_path(tmp_path, report, "modelPath")
    manifest_path = _artifact_path(tmp_path, report, "manifestPath")
    assert model_path.is_file()
    assert manifest_path.is_file()
    assert model_path.parent == manifest_path.parent
    assert model_path.parent.parent == tmp_path / ".femagent" / "generated-models"

    source = model_path.read_text(encoding="utf-8")
    assert 'import openseespy.opensees as ops\n' in source
    assert 'ops.wipe()\n' in source
    assert 'ops.model("basic", "-ndm", 2, "-ndf", 3)\n' in source
    assert 'ops.node(1, 0.0, 0.0)\n' in source
    assert 'ops.node(2, 6.0, 0.0)\n' in source
    assert 'ops.node(3, 6.0, 4.0)\n' in source
    assert 'ops.node(4, 0.0, 4.0)\n' in source
    assert 'ops.fix(1, 1, 1, 1)\n' in source
    assert 'ops.fix(2, 1, 1, 1)\n' in source
    assert source.count('ops.geomTransf("Linear", 1)') == 1
    assert 'ops.element("elasticBeamColumn", 1, 1, 4, 0.02, 206000000000.0, 8e-05, 1)\n' in source
    assert 'ops.element("elasticBeamColumn", 2, 4, 3, 0.02, 206000000000.0, 8e-05, 1)\n' in source
    assert 'ops.element("elasticBeamColumn", 3, 3, 2, 0.02, 206000000000.0, 8e-05, 1)\n' in source
    for forbidden in (
        "ops.timeSeries(",
        "ops.pattern(",
        "ops.constraints(",
        "ops.numberer(",
        "ops.system(",
        "ops.test(",
        "ops.algorithm(",
        "ops.integrator(",
        "ops.analysis(",
        "ops.analyze(",
        "ops.eigen(",
    ):
        assert forbidden not in source

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest == report


def test_invalid_spec_is_blocked_without_publishing_artifacts(tmp_path: Path) -> None:
    spec = _load_spec()
    spec["elements"][0]["nodeJ"] = 999

    report = render_opensees_frame_2d(tmp_path, spec)

    assert report["status"] == "BLOCKED"
    assert report["reason"] == "MODEL_NOT_READY"
    assert report["readiness"]["status"] == "INVALID_SPEC"
    assert report["renderId"] is None
    assert report["artifacts"] is None
    assert report["renderFingerprint"] is None
    assert not (tmp_path / ".femagent" / "generated-models").exists()


def test_not_ready_spec_is_blocked_without_publishing_artifacts(tmp_path: Path) -> None:
    spec = _load_spec()
    spec["constraints"] = []

    report = render_opensees_frame_2d(tmp_path, spec)

    assert report["status"] == "BLOCKED"
    assert report["reason"] == "MODEL_NOT_READY"
    assert report["readiness"]["status"] == "NOT_READY"
    assert report["artifacts"] is None
    assert not (tmp_path / ".femagent" / "generated-models").exists()


def test_equivalent_collection_order_produces_identical_rendered_content(tmp_path: Path) -> None:
    original = _load_spec()
    reordered = deepcopy(original)
    for key in ("nodes", "materials", "sections", "elements", "constraints", "nodalMasses"):
        reordered[key] = list(reversed(reordered[key]))
    for constraint in reordered["constraints"]:
        constraint["dofs"] = list(reversed(constraint["dofs"]))

    first = render_opensees_frame_2d(tmp_path, original)
    second = render_opensees_frame_2d(tmp_path, reordered)

    assert first["renderId"] != second["renderId"]
    assert _artifact_path(tmp_path, first, "modelPath").read_bytes() == _artifact_path(
        tmp_path, second, "modelPath"
    ).read_bytes()
    assert first["artifacts"]["modelSha256"] == second["artifacts"]["modelSha256"]
    assert first["renderFingerprint"] == second["renderFingerprint"]
    assert first["input"]["modelSpecFingerprint"] == second["input"]["modelSpecFingerprint"]


def test_constraints_and_nodal_mass_map_only_from_explicit_dofs_and_values(tmp_path: Path) -> None:
    spec = _load_spec()
    spec["constraints"] = [
        {"nodeId": 1, "dofs": ["UX", "UY"]},
        {"nodeId": 2, "dofs": ["UY"]},
    ]
    spec["nodalMasses"] = [{"nodeId": 3, "mUX": 1200.0, "mUY": 1500.0}]

    report = render_opensees_frame_2d(tmp_path, spec)
    source = _rendered_source(tmp_path, report)

    assert report["status"] == "RENDERED"
    assert 'ops.fix(1, 1, 1, 0)\n' in source
    assert 'ops.fix(2, 0, 1, 0)\n' in source
    assert 'ops.mass(3, 1200.0, 1500.0, 0.0)\n' in source
    assert "ops.mass(1," not in source
    assert "ops.mass(2," not in source
    assert "ops.mass(4," not in source


def test_rz_constraint_maps_to_third_opensees_dof(tmp_path: Path) -> None:
    spec = _load_spec()
    spec["constraints"] = [
        {"nodeId": 1, "dofs": ["RZ"]},
        {"nodeId": 2, "dofs": ["UX", "UY"]},
    ]

    report = render_opensees_frame_2d(tmp_path, spec)
    source = _rendered_source(tmp_path, report)

    assert report["status"] == "RENDERED"
    assert 'ops.fix(1, 0, 0, 1)\n' in source
    assert 'ops.fix(2, 1, 1, 0)\n' in source


def test_negative_zero_renders_as_canonical_zero(tmp_path: Path) -> None:
    spec = _load_spec()
    spec["nodes"][0]["x"] = -0.0

    report = render_opensees_frame_2d(tmp_path, spec)
    source = _rendered_source(tmp_path, report)

    assert report["status"] == "RENDERED"
    assert 'ops.node(1, 0.0, 0.0)\n' in source
    assert "-0.0" not in source


def test_non_object_spec_fails_with_stable_error(tmp_path: Path) -> None:
    with pytest.raises(FemCoreError) as raised:
        render_opensees_frame_2d(tmp_path, [])  # type: ignore[arg-type]

    assert raised.value.code == "OPENSEES_RENDER_SPEC_NOT_OBJECT"


def test_unsupported_ready_profile_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = _load_spec()
    original = renderer_module.evaluate_engineering_model_readiness(spec)
    monkeypatch.setattr(
        renderer_module,
        "evaluate_engineering_model_readiness",
        lambda _spec: {**original, "status": "READY", "profile": "UNSUPPORTED_PROFILE"},
    )

    with pytest.raises(FemCoreError) as raised:
        render_opensees_frame_2d(tmp_path, spec)

    assert raised.value.code == "OPENSEES_RENDER_UNSUPPORTED_PROFILE"
    assert not (tmp_path / ".femagent" / "generated-models").exists()


def test_existing_render_directory_is_never_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = _load_spec()
    render_id = "render_0123456789abcdef"
    collision = tmp_path / ".femagent" / "generated-models" / render_id
    collision.mkdir(parents=True)
    marker = collision / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(renderer_module, "_new_render_id", lambda: render_id)

    with pytest.raises(FemCoreError) as raised:
        render_opensees_frame_2d(tmp_path, spec)

    assert raised.value.code == "OPENSEES_RENDER_ARTIFACT_EXISTS"
    assert marker.read_text(encoding="utf-8") == "keep"


def test_failed_publication_removes_fresh_render_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _load_spec()
    original_write_text = renderer_module._write_text
    writes = 0

    def fail_second_write(path: Path, content: str) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("synthetic manifest write failure")
        original_write_text(path, content)

    monkeypatch.setattr(renderer_module, "_write_text", fail_second_write)

    with pytest.raises(FemCoreError) as raised:
        render_opensees_frame_2d(tmp_path, spec)

    assert raised.value.code == "OPENSEES_RENDER_WRITE_FAILED"
    generated = tmp_path / ".femagent" / "generated-models"
    assert generated.is_dir()
    assert list(generated.iterdir()) == []
