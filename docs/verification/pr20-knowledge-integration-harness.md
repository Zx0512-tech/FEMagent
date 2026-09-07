# PR20 — Knowledge Integration Harness Verification

Date: 2026-09-07
Roadmap label: PR20
GitHub pull request: #16
Branch: `feat/pr20-knowledge-integration-harness`
Base: `main`

## Scope verified

PR20 implements a deterministic fixture-backed knowledge integration boundary. It does not integrate live RAGFlow and makes no retrieval-quality claim.

Production scope is limited to:

- `@femagent/knowledge-client` provider-neutral contracts;
- strict workspace-bounded fixture provider;
- citation-oriented `KnowledgeEvidence`;
- `FEMAGENT_UNIFIED_EVIDENCE_V1` aggregation;
- SAFE/read-only `engiknow_search` Pi tool;
- agent entrypoint registration;
- fixture and integration tests.

No `fem_core` production file, solver adapter, Result Intelligence implementation, Semantic Role implementation, or solver execution path is modified by PR20.

## TDD evidence

### RED 1 — provider contract

Commit: `323ce79b7220b2a94ecaa48aac5d1897a8d650a5`
GitHub Actions: CI #308, run `34078479881`

Expected failure occurred at TypeScript typecheck:

```text
TS2307: Cannot find module '@femagent/knowledge-client'
```

This established the missing provider package/API before production implementation.

### GREEN 1 — fixture provider

Commit: `1e07c86e024bf9e41e3edac4810d2fed68b24cd2`
GitHub Actions: CI #309, run `34078732504`
Result: `completed / success`

The run passed typecheck, TypeScript tests, Python regression tests, Ruff, OpenSees adapter smoke, ANSYS result-reader smoke, and FEM health smoke.

### RED 2 — unified evidence

Commit: `db91659d785a3e74797b150fc7bafda3d315d934`
GitHub Actions: CI #310, run `34078895131`

Expected failure occurred at TypeScript typecheck:

```text
TS2305: Module '"@femagent/knowledge-client"' has no exported member 'composeUnifiedEvidenceBundle'.
```

This established the missing unified evidence composition API before implementation.

### GREEN 2 — integration harness

Implementation commit: `b3929b49159fd7043a30517788248c317cc38419`
GitHub Actions: CI #311, run `34079069196`
Result: `completed / success`

Observed results:

```text
TypeScript: 30 tests, 30 passed, 0 failed
Python:     172 passed
Ruff:       All checks passed
OpenSees adapter availability smoke: passed
ANSYS result-reader import smoke:    passed
FEM health smoke:                    passed
```

Python emitted 300 existing NumPy/VTK deprecation warnings across ANSYS/result-reader tests; they did not fail the suite and PR20 does not modify the affected Python code.

## Golden Path assertions

The integration harness uses the production `runFemEvidenceProject()` path against recorded OpenSees-style result artifacts.

The test proves:

- Engineering Evidence status is `VERIFIED`;
- verified displacement `absolutePeak` is `0.03`;
- fixture Knowledge Evidence status is `RETRIEVED`;
- fixture text deliberately contains synthetic value `9999`;
- unified evidence preserves the original Engineering Evidence object and keeps `0.03` unchanged;
- malformed fixture retrieval raises `INVALID_KNOWLEDGE_FIXTURE` without mutating an already verified Engineering Evidence report.

Therefore knowledge content is integrated as citation evidence but cannot overwrite FEM numerical truth.

## Provider security/fail-closed assertions

TypeScript tests cover:

- missing provider configuration;
- unsupported provider mode;
- absolute/workspace-escaping fixture paths;
- missing fixture files;
- malformed fixture JSON/schema;
- empty query;
- invalid `topK` outside 1–20;
- deterministic case-insensitive exact matching;
- empty successful no-match result;
- explicit knowledge-base filtering;
- stable citation/retrieval metadata;
- `queryId` dependence on fixture content digest.

## Architecture boundary audit

Compared with `main`, the implementation introduces no live RAGFlow client, HTTP retrieval path, embedding dependency, reranker dependency, or query-rewrite subsystem.

`KnowledgeEvidence` uses `RETRIEVED | LIMITED`; it does not reuse Engineering Evidence `VERIFIED` semantics.

`composeUnifiedEvidenceBundle()` includes `engineeringReport.verifiedEvidence` directly and does not recalculate engineering values, infer units, rewrite targets, change provenance, or alter artifact hashes.

## Final exact-head gate

This verification document is part of the PR itself, so the authoritative final-head verification is the GitHub Actions CI run attached to the final PR head after documentation is committed. The PR conversation/body records that final head SHA and run ID before the draft is marked ready for review.
