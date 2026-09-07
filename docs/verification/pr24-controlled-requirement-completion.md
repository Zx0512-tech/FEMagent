# PR24 — Controlled Requirement Completion Verification

Date: 2026-09-07
PR: #20
Branch: `feat/pr24-controlled-requirement-completion`
Base: `main`

## Scope verified

PR24 adds the evidence-backed completion path:

```text
natural-language/project statements
→ Agent extraction into source-backed RequirementDraft
→ deterministic Python evidence admission and completion
→ COMPLETE / INCOMPLETE / CONFLICT / INVALID_DRAFT
→ candidate EngineeringModelSpec only on COMPLETE
→ PR21 validation
→ PR22 readiness
→ PR23 rendering only when READY
```

The completion layer does not execute a solver, write model artifacts, infer arbitrary engineering values, or convert RAG/LLM prose into engineering truth.

## Provenance and fail-closed assertions

Tests and source-level safety contracts require:

- every `USER_EXPLICIT` fact to carry an exact source ID and exact quote;
- quote containment and kind-specific numeric/unit/relation evidence validation;
- derived facts to remain labeled `TEMPLATE_DERIVED` or `DETERMINISTIC_DERIVED`;
- only the six named V1 deterministic derivations to add facts;
- missing `E`, `A`, `Iz`, force/time units, arbitrary topology, and arbitrary support conditions never to be guessed;
- contradictory admissible facts to produce `CONFLICT` instead of silent precedence/overwrite;
- malformed source/evidence contracts to produce `INVALID_DRAFT`;
- unresolved required facts to produce `INCOMPLETE` with `candidateModelSpec = null`;
- only `COMPLETE` to return a candidate that has passed the internal PR21 validation invariant.

The three V1 beam templates are convenience rules, not a global model whitelist. A fully explicit no-template V1 frame path is also covered by regression tests.

## TDD evidence

Implementation used staged RED/GREEN gates.

Representative RED commits:

```text
2f378070f0e8d31bd1907cbfc5947a9fe5346e7b  requirement draft RED tests
f8ec30a17bcd0fbf1a38a6c1bfd0544ebe2448f0  controlled template RED tests
0e78d723696d15dccb83b31dcf82771cc76d0690  completion engine RED tests
11839536739c3a07e03cba94bcc1a714645bcb6a  bridge command RED tests
1c80c210b152451fcd29cca3a78fdeda33088d95  TypeScript transport RED tests
200b08959a48da50434625b7e59c01ccfc8f7fd9  Pi tool safety/registration RED tests
```

Observed staged CI evidence:

- CI #396 exposed a real evidence-normalization defect: Unicode NFKC collapsed dimensional superscripts, making valid `m²/m⁴` property evidence ambiguous. The fix preserved dimensional unit tokens rather than weakening evidence rules.
- CI #397 completed the requirement-completion core GREEN gate.
- CI #398 bridge RED failed only because `requirement.complete` was not yet registered; existing Python behavior remained green.
- CI #399 completed the bridge GREEN gate.
- CI #400 TypeScript RED failed on the intentionally missing completion exports/helper.
- CI #403 then identified a test-construction issue where `.map()` erased the discriminated `dimension → unit value` relationship; production types were intentionally kept strict and the test was corrected.
- CI #404 completed the real TypeScript→Python transport GREEN gate.
- CI #405 ran the existing TypeScript suite successfully except for exactly the two new Pi registration/allow-list assertions, which failed because the extension and Agent wiring did not yet exist.
- CI #407 completed the SAFE Pi tool/Agent GREEN gate.

These stages preserve the principle that production behavior is added only after the intended failure mode is observed.

## PR21 → PR22 → PR23 integration proof

`tests/python/test_requirement_completion_integration.py` uses production APIs and an explicitly evidenced simple-support beam:

```text
span = 15 m
units = m / N / s
E = 2.06e11 Pa
A = 0.02 m²
Iz = 8e-5 m⁴
```

The positive integration test requires the exact chain:

```text
completion.status = COMPLETE
candidateModelSpec != null
PR21 validation = VALID
PR22 readiness = READY
PR23 render = RENDERED
Model Intelligence classification = MODEL_CONFIRMED
dynamicGeneration = false
static topology = 2 nodes / 1 element
```

It also reads generated `model.py` and requires absence of analysis/load commands including `timeSeries`, `pattern`, `integrator`, `algorithm`, `analysis`, `analyze`, and `eigen`.

The negative integration test uses only:

```text
建立一个15m简支梁
```

and requires:

```text
completion.status = INCOMPLETE
candidateModelSpec = null
modelSpecFingerprint = null
no generated-model artifact directory
```

Thus incomplete natural-language intent cannot jump directly into PR23 rendering.

## Pre-documentation full CI evidence

Task 7 integration commit:

```text
38667f4eb875961a36aa1f4aa83006d31d33863a
```

GitHub Actions CI #408, run ID `34101011212`, completed successfully with all workflow steps green:

```text
TypeScript typecheck: PASS
TypeScript engineering bridge tests: PASS
Python engineering core tests: PASS
Python lint / Ruff: PASS
OpenSees adapter availability smoke: PASS
ANSYS result reader import smoke: PASS
Health smoke: PASS
```

This run proves the completed implementation and integration tests before final architecture/verification documentation changed the branch head.

## Final verification commands

The CI-equivalent verification surface is:

```bash
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
python -c "from fem_core.solvers import get_solver_adapter; s=get_solver_adapter('opensees').status(); assert s['available'], s"
python -c "from ansys.mapdl import reader; assert callable(reader.read_binary)"
pnpm fem:health
```

Evidence categories required from the final exact-head GitHub CI are:

```text
TypeScript typecheck PASS
TypeScript tests PASS
Python tests PASS
Ruff PASS
OpenSees availability smoke PASS
ANSYS result-reader smoke PASS
fem:health status = ok
```

## Diff boundary to verify at closeout

The final `main...feat/pr24-controlled-requirement-completion` diff must remain limited to PR24 requirement-completion code, transport/tool wiring, tests, and documentation.

It must not change production semantics for:

```text
PR21 ModelSpec validation
PR22 readiness
PR23 renderer mapping
solver adapters
ANSYS behavior
Result Intelligence
Load Intelligence
Knowledge/RAG truth separation
Semantic Roles
cross-solver validation
optimization
```

Before the final documentation commits, the branch diff already satisfied this boundary: no production file from those subsystems was modified. The final boundary is rechecked after this verification document is committed.

## Final exact-head gate

This document changes the branch head, so CI #408 is intentionally **not** treated as final-head proof.

PR24 is ready for review only after the pull-request-triggered GitHub CI for the final documentation head completes `success`, its individual steps/logs are inspected, and the final diff boundary is confirmed. The final head SHA and exact-head CI run ID/result are recorded in PR #20 metadata/body after that run so recording the evidence does not mutate the verified Git head.

## Authority boundary

`COMPLETE` proves deterministic requirement completion plus PR21 candidate validity only. It does not prove PR22 readiness, renderer success, solver-domain construction, structural adequacy, analysis success, or numerical results.

PR24 remains a controlled information-completion layer, not an autonomous engineering-design authority.
