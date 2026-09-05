from fem_core.evidence import EvidenceStatus, project_claim
from fem_core.evidence.report import project_engineering_report


def test_report_promotes_only_verified_evidence():
    verified = project_claim(
        "EVID-101",
        "Maximum displacement at Node 2",
        "result.rst",
        "sha256",
        {"value": 12.5, "unit": "mm"},
    )
    limited = project_claim(
        "EVID-102",
        "Result exists without checksum",
        "result.rst",
        None,
    )

    report = project_engineering_report(
        "bridge-demo",
        [verified, limited],
        [{"runId": "run001", "solver": "ANSYS"}],
    )

    assert len(report["verifiedEvidence"]) == 1
    assert report["verifiedEvidence"][0]["evidenceId"] == "EVID-101"
    assert report["limitations"][0]["status"] == EvidenceStatus.LIMITED.value


def test_report_does_not_create_claims_from_text():
    evidence = project_claim(
        "EVID-103",
        "AI generated displacement summary",
        None,
        None,
    )

    report = project_engineering_report("demo", [evidence])

    assert report["verifiedEvidence"] == []
    assert report["limitations"][0]["status"] == EvidenceStatus.UNVERIFIED.value
