# PR29 — ANSYS V2 Uniform-Base Earthquake Execution Design

## Goal

Admit a validated EngineeringAnalysisSpec V2 `TRANSIENT + UNIFORM_BASE_EXCITATION` intent to an existing, explicitly confirmed ANSYS APDL Model Bundle and execute it through the existing generic ANSYS SolverAdapter without adding a new LLM-visible execution tool.

PR29 is intentionally narrow: X/Y uniform-support acceleration, explicit NONE or RAYLEIGH damping, deterministic fixed-step full transient controls, and result requests limited to nodal DISPLACEMENT and restrained-node REACTION_FORCE.

## Architecture

```text
EngineeringAnalysisSpec V2
        +
ANSYS APDL Model Bundle
        +
explicit bundle confirmation
        ↓
ANSYS V2 admission
        ↓
artifact/hash/time/channel verification
        ↓
APDL transient-hook + solve-hook verification
        ↓
deterministic staged load/control injection
        ↓
existing solver.preflight / solver.run
        ↓
ANSYS .rst
        ↓
existing Result Intelligence
```

The raw APDL Model Bundle remains the solver model truth. PR29 does not claim that an arbitrary APDL bundle is semantically equivalent to the EngineeringModelSpec referenced by AnalysisSpec.modelSpecFingerprint. Instead, the caller must provide the exact current APDL bundle fingerprint as an explicit confirmation. The run manifest records both identities and the binding mode `EXPLICIT_BUNDLE_CONFIRMATION`.

## Public execution surface

No new solver-specific Pi execution tool is added.

Existing generic tools remain authoritative:

- `fem_solver_preflight`
- `fem_solver_run`

ANSYS V2 context travels through `solverOptions.ansysV2`:

```json
{
  "modelUnits": {"length": "m", "time": "s"},
  "ansysV2": {
    "analysisSpec": {"schemaVersion": "2.0", "...": "..."},
    "confirmedBundleFingerprint": "<sha256>"
  }
}
```

For this mode, external `loadPath` is forbidden. The load artifact is taken only from the validated AnalysisSpec and re-read/re-hashed immediately before execution.

## Supported profile

Exactly:

- AnalysisSpec schemaVersion: `2.0`
- analysisType: `TRANSIENT`
- excitation.type: `UNIFORM_BASE_EXCITATION`
- excitation.component: `X | Y`
- excitation.quantity: `ACCELERATION`
- load artifact: one-channel `FEMAGENT_LOAD_CSV_V1`
- damping: `NONE | RAYLEIGH`
- result quantities:
  - NODE `DISPLACEMENT` X/Y
  - NODE `REACTION_FORCE` X/Y

Not supported in PR29:

- Z excitation for the current 2D engineering profile
- nodal-force transient
- static/modal ANSYS V2
- response spectrum
- multiple-support excitation
- ABSOLUTE_ACCELERATION / RELATIVE_ACCELERATION result requests
- nonlinear transient analysis
- automatic unit inference
- automatic damping inference
- automatic ModelSpec ↔ APDL equivalence claims
- optimization

## Admission truth

Admission must fail closed unless all are true:

1. AnalysisSpec is intrinsically VALID V2.
2. Profile is exactly the supported uniform-base transient profile.
3. Current APDL bundle fingerprint equals `confirmedBundleFingerprint`.
4. Model units are explicit and supported.
5. AnalysisSpec load artifact exists, remains inside workspace, and matches declared SHA-256.
6. Canonical load channel matches the AnalysisSpec component and acceleration semantics.
7. Canonical load starts at zero, uses the requested fixed step, and ends at requested duration after deterministic unit conversion.
8. APDL bundle exposes exactly one `ANTYPE,TRANS` hook and at least one explicit solve command.
9. Existing active `ACEL` is absent.
10. Existing active Rayleigh/global damping commands are absent, so PR29 owns damping truth.
11. Requested result node IDs are statically enumerable in the APDL bundle.
12. REACTION_FORCE requests target a statically explicit restrained node/DOF.
13. Only the supported result quantities/components are requested.

Parameterized/block-based/include-driven models that cannot provide deterministic static node/constraint identity remain outside this first ANSYS V2 admission profile.

## Deterministic staged injection

The source Model Bundle is never modified.

The staged bundle receives:

- the already-proven canonical acceleration table/macro;
- a deterministic PR29 control block inserted immediately before the verified solve command.

The control block owns:

- `TRNOPT,FULL`
- `AUTOTS,OFF`
- `DELTIM,<AnalysisSpec timeStep>`
- `TIME,<AnalysisSpec duration>`
- `ALPHAD/BETAD` for RAYLEIGH, or explicit zero Rayleigh terms for NONE
- `OUTRES,NSOL,ALL`
- `OUTRES,RSOL,ALL`

The existing canonical `ACEL` table macro remains the only support-acceleration input.

## Provenance

Preflight and run record:

- AnalysisSpec fingerprint
- declared ModelSpec fingerprint from AnalysisSpec
- confirmed/current ANSYS bundle fingerprint
- load artifact path/SHA
- fixed-step/duration evidence
- model-unit conversions
- damping mode/coefficients
- staged-control fingerprint
- execution input fingerprint
- generated load table/macro hashes
- final binary result hash when present

## Result semantics

PR29 does not invent a second result layer. Existing Result Intelligence reads the recorded ANSYS binary result.

Because ANSYS result units are not independently encoded/proven by the legacy reader, Result Intelligence continues to return `unit: null` for ANSYS numerical values. PR29 records model units in run provenance but does not silently rewrite result units.

## Verification while GitHub Actions quota is exhausted

All RED/GREEN tests are committed and remain the acceptance contract. Fresh GitHub Actions is deferred until quota is restored. The PR remains Draft until the standard repository verification suite can run.
