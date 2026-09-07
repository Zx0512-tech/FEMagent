from __future__ import annotations

import json
from pathlib import Path

from fem_core.model_spec import render_opensees_frame_2d
from fem_core.model_spec.opensees_source import build_opensees_frame_2d_model_source
from fem_core.model_spec.validator import validate_engineering_model_spec

FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def test_shared_model_source_matches_pr23_rendered_model(tmp_path: Path) -> None:
    spec = json.loads(FIXTURE.read_text(encoding="utf-8"))
    validation = validate_engineering_model_spec(spec)
    assert validation["status"] == "VALID"
    normalized = validation["normalizedSpec"]
    assert isinstance(normalized, dict)

    expected = build_opensees_frame_2d_model_source(normalized)
    report = render_opensees_frame_2d(tmp_path, spec)

    assert report["status"] == "RENDERED"
    model_path = tmp_path / report["artifacts"]["modelPath"]
    assert model_path.read_text(encoding="utf-8") == expected
