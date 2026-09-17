from __future__ import annotations

import pytest

from fem_core.errors import FemCoreError
from fem_core.solvers.admission import admit_analysis_execution


def test_opensees_modal_is_admitted() -> None:
    report = admit_analysis_execution(
        solver="opensees",
        profile="OPENSEES_FRAME_2D_MODAL_V2",
        requested_quantities=["EIGENVALUE", "MODE_SHAPE"],
    )

    assert report["status"] == "ADMITTED"
    assert report["solver"] == "OPENSEES"


def test_unsupported_profile_is_rejected() -> None:
    with pytest.raises(FemCoreError) as exc:
        admit_analysis_execution(
            solver="opensees",
            profile="OPENSEES_NONLINEAR_CONTACT_V1",
        )

    assert exc.value.code == "SOLVER_PROFILE_UNSUPPORTED"


def test_unsupported_result_is_rejected() -> None:
    with pytest.raises(FemCoreError) as exc:
        admit_analysis_execution(
            solver="opensees",
            profile="OPENSEES_FRAME_2D_MODAL_V2",
            requested_quantities=["STRESS_TENSOR"],
        )

    assert exc.value.code == "SOLVER_RESULT_UNSUPPORTED"
