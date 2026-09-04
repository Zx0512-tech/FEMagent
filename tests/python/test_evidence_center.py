from fem_core.evidence import EvidenceStatus, project_claim


def test_claim_with_artifact_is_verified():
    evidence = project_claim(
        "EVID-001",
        "Maximum displacement occurs at Node 2",
        "result.rst",
        "abc123",
        {"value": 12.5, "unit": "mm"},
    )

    assert evidence.status == EvidenceStatus.VERIFIED


def test_claim_without_artifact_is_not_verified():
    evidence = project_claim(
        "EVID-002",
        "AI summary maximum displacement",
        None,
        None,
    )

    assert evidence.status == EvidenceStatus.UNVERIFIED


def test_artifact_without_hash_is_limited():
    evidence = project_claim(
        "EVID-003",
        "Result exists",
        "result.rst",
        None,
    )

    assert evidence.status == EvidenceStatus.LIMITED
