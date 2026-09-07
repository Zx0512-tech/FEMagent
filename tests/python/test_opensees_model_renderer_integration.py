from __future__ import annotations

import json
from pathlib import Path
from unittest import SkipTest

from fem_core.model_spec import render_opensees_frame_2d
from fem_core.opensees_python_inspection import inspect_opensees_python
from fem_core.solvers.opensees_python import OpenSeesBundleAdapter

FIXTURE = Path("tests/fixtures/model_spec/simple-portal-frame.json")


def _load_spec() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_rendered_model_is_confirmed_by_existing_static_model_intelligence(tmp_path: Path) -> None:
    spec = _load_spec()
    report = render_opensees_frame_2d(tmp_path, spec)
    assert report["status"] == "RENDERED"

    inspection = inspect_opensees_python(tmp_path, report["artifacts"]["modelPath"])

    assert inspection["classification"] == "MODEL_CONFIRMED"
    assert inspection["dynamicGeneration"] is False
    assert inspection["safetyFindings"] == []
    assert inspection["staticTopology"] == {
        "nodeCount": 4,
        "elementCount": 3,
        "nodeTags": [1, 2, 3, 4],
        "elementTags": [1, 2, 3],
        "basis": "LITERAL_AST_CALLS",
    }
    assert inspection["bundle"]["integrity"] == "VALID"


def test_rendered_model_build_only_realizes_expected_domain_without_analysis(tmp_path: Path) -> None:
    spec = _load_spec()
    report = render_opensees_frame_2d(tmp_path, spec)
    assert report["status"] == "RENDERED"

    adapter = OpenSeesBundleAdapter()
    if not adapter.status()["available"]:
        raise SkipTest("OpenSeesPy is not available in this environment")

    build = adapter.build_inspect(tmp_path, model_path=report["artifacts"]["modelPath"])

    assert build["analysisAdvanced"] is False
    assert build["interceptedAnalyzeCalls"] == 0
    assert build["nodeTags"] == [1, 2, 3, 4]
    assert build["elementTags"] == [1, 2, 3]
    assert build["nodeCoordinates"] == {
        "1": [0.0, 0.0],
        "2": [6.0, 0.0],
        "3": [6.0, 4.0],
        "4": [0.0, 4.0],
    }
