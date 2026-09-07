# PR21 — Engineering Model Specification V1 Verification

Date: 2026-09-07
Roadmap label: PR21
GitHub pull request: #17
Branch: `feat/pr21-engineering-model-spec-v1`
Base: `main`

## Scope verified

PR21 introduces a deterministic, solver-neutral `EngineeringModelSpec` validation boundary for controlled 2D planar elastic frame authoring.

Production scope is limited to:

- Python-authoritative `fem_core.model_spec` validation;
- strict 2D planar FRAME V1 schema with `UX`, `UY`, `RZ` degrees of freedom;
- explicit units and fail-closed unknown fields;
- deterministic normalization and SHA256 `modelSpecFingerprint`;
- stable validation issue codes and `VALID | INVALID` results;
- bridge command `modelSpec.validate`;
- TypeScript ModelSpec transport contracts and `runFemModelSpecValidate()`;
- SAFE/read-only Pi tool `fem_model_spec_validate`;
- agent entrypoint registration;
- one deterministic portal-frame fixture and Python/TypeScript regression tests;
- architecture and implementation documentation.

PR21 does **not** render OpenSees or ANSYS model files, write solver models, execute solvers, run analysis, infer loads, create Semantic Roles, or make numerical engineering claims.

## TDD evidence

### RED 1 — Python ModelSpec core

CI #319 failed as intended because the production module did not yet exist:

```text
ModuleNotFoundError: No module named 'fem_core.model_spec'
```

This established the missing deterministic ModelSpec core before implementation.

### GREEN 1 — Python ModelSpec core

CI #323 completed successfully after the minimal Python validator implementation and Ruff-only cleanup.

At this stage the ModelSpec behavior tests were green while the existing TypeScript suite remained green.

### RED 2 — bridge contract

CI #325 failed as intended with `UNKNOWN_COMMAND` for `modelSpec.validate` while the fingerprint regression test already passed.

This established the missing bridge command before bridge implementation.

### GREEN 2 — bridge contract

Commit: `a644a4b8f76a5b66bd4267855766750e213d6e87`
GitHub Actions: CI #326, run `34082425346`
Result: `completed / success`

The bridge accepts an object `spec`, returns typed validation results for engineering-invalid ModelSpecs, and uses `INVALID_ARGUMENT` only when `spec` itself is not a JSON object.

### RED 3 — TypeScript contract

Commit: `0bbb406952fc4914bb3b9807f45953fb13bfb113`
GitHub Actions: CI #327, run `34082523415`

Expected typecheck failures included:

```text
Module '"@femagent/fem-tools"' has no exported member 'runFemModelSpecValidate'.
Module '"@femagent/fem-tools"' has no exported member 'FemEngineeringModelSpecInput'.
```

This established the missing TypeScript transport contract before implementation.

### GREEN 3 — TypeScript bridge

Implementation commits include:

- `f682996f7d0ef2aecd26865261d5c59d8db7674b` — ModelSpec TypeScript contracts;
- `3508d604f66c4961eca5689dd562853b5860dfc5` — Python bridge wrapper;
- `87fc50d274a9fa7c5102e7d3462a99c18c75472e` — package exports.

GitHub Actions: CI #330, run `34082676430`
Result: `completed / success`

TypeScript remains a strongly typed transport layer; it does not duplicate or replace Python engineering validation.

### RED 4 — Pi tool / agent registration

Commit: `ac2ea9f4db03f066a94da5cf4ff2afafca701465`
GitHub Actions: CI #331, run `34082770715`

Expected failures were limited to the newly introduced registration tests:

- `.pi/extensions/model-spec-tools.ts` did not exist;
- the Agent entrypoint had not loaded or allow-listed `fem_model_spec_validate`.

The existing ModelSpec TypeScript/Python bridge tests remained green in the same run.

### GREEN 4 — SAFE public tool

Implementation commits:

- `544318964daab2812842cac517a83dafb13752c8` — SAFE/read-only ModelSpec validation extension;
- `53214ed52be371d9a7fd7f03435c68b2d5c3e00f` — Agent registration.

GitHub Actions: CI #333, run `34082894936`
Result: `completed / success`

Observed results:

```text
TypeScript: 34 tests, 34 passed, 0 failed
Python:     190 passed
Ruff:       All checks passed
OpenSees adapter availability smoke: passed
ANSYS result-reader import smoke:    passed
FEM health smoke:                    passed
```

Python emitted 300 existing NumPy/VTK deprecation warnings in ANSYS/result-reader tests. They did not fail the suite, and PR21 does not modify the affected dependency code.

## Deterministic ModelSpec assertions

The test suite covers the V1 engineering contract including:

- strict top-level and nested schema validation;
- 2D planar FRAME-only scope;
- explicit model units;
- unique IDs for nodes/materials/sections/elements;
- element node/material/section reference integrity;
- duplicate and missing entity detection;
- constraint node and degree-of-freedom validity;
- lumped mass validity;
- normalization of entity ordering;
- stable SHA256 `modelSpecFingerprint`;
- fingerprint invariance under semantically irrelevant input ordering;
- fingerprint change when engineering content changes;
- typed invalid results instead of bridge/process failure for ordinary engineering validation errors.

The canonical fixture is `tests/fixtures/model_spec/simple-portal-frame.json`.

## Authority boundary audit

Python `fem_core.model_spec` remains the sole authoritative engineering validator.

The TypeScript package transports typed requests/results across the existing versioned bridge. The Pi extension invokes `runFemModelSpecValidate()` and does not call `runFemSolverRun`, render APDL/OpenSees code, modify model files, or bypass validation.

Compared with `main`, PR21 does not modify solver adapters, Result Intelligence, Load Intelligence, Semantic Roles, Engineering Evidence, Cross-Solver Validation, or the RAG/knowledge provider implementation.

## Architecture position after PR21

PR21 establishes:

```text
engineering facts
    ↓
EngineeringModelSpec
    ↓
fem_model_spec_validate
    ↓
Python deterministic validator
    ↓
VALID / INVALID
+ normalizedSpec
+ modelSpecFingerprint
```

It intentionally stops before solver rendering. OpenSees and ANSYS renderers belong to later roadmap work.

## Pre-closeout verification

Architecture documentation commit:

- `154e603519b3f2008a81f3f8ebbde6133d085748` — `docs/architecture/engineering-model-spec.md`

GitHub Actions: CI #334, run `34083075867`
Result: `completed / success`

## Final exact-head gate

This verification document is part of the PR itself, so the authoritative closeout evidence is the GitHub Actions CI run attached to the PR head **after this document is committed**.

The PR body/conversation records that final head SHA and workflow run ID before the Draft PR is marked Ready for Review. No completion claim should rely only on an earlier green commit.
