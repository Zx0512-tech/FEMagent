from fem_core.evidence import EvidenceStatus
from fem_core.evidence.result_projection import project_result_evidence


def test_result_with_artifact_provenance_becomes_verified():
    evidence = project_result_evidence(
        evidence_id="EVID-R-001",
        result={"node": 2, "component": "UX", "value": 12.5, "unit": "mm"},
        artifact="result.rst",
        artifact_sha256="sha256-result",
    )

    assert evidence.status == EvidenceStatus.VERIFIED


def test_result_without_artifact_cannot_be_verified():
    evidence = project_result_evidence(
        evidence_id="EVID-R-002",
        result={"value": 12.5, "unit": "mm"},
        artifact=None,
        artifact_sha256=None,
    )

    assert evidence.status == EvidenceStatus.UNVERIFIED


def test_result_without_hash_is_limited():
    evidence = project_result_evidence(
        evidence_id="EVID-R-003",
        result={"value": 12.5},
        artifact="result.rst",
        artifact_sha256=None,
    )

    assert evidence.status == EvidenceStatus.LIMITED
