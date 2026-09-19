# PR29 Verification — ANSYS V2 Uniform-Base Earthquake Execution

## Status

**Implementation complete; fresh full-suite verification is green.**

Fresh GitHub Actions CI #633 (run id `35351009091`) completed successfully on the implementation head after the PR28 bridge-compatibility sync and PR29 Ruff fixes.

## Implemented acceptance surface

- EngineeringAnalysisSpec V2 `TRANSIENT + UNIFORM_BASE_EXCITATION` ANSYS admission.
- X/Y canonical acceleration artifact verification from the AnalysisSpec path/SHA.
- Exact APDL bundle fingerprint binding with the limitation `semanticEquivalence=NOT_MACHINE_PROVEN`.
- Explicit APDL node-target identity policy.
- Fixed-step time-origin / dt / duration checks.
- Explicit `NONE | RAYLEIGH` damping ownership and source damping-conflict rejection.
- NODE `DISPLACEMENT` and restrained-node `REACTION_FORCE` X/Y result-request admission.
- One verified transient hook and one verified solve hook.
- Staged-only canonical `ACEL` load injection.
- Staged-only deterministic analysis-control macro before the verified solve command.
- Existing generic `solver.preflight` / `solver.run` tool surface only.
- Run-manifest admission/load/control/bundle/artifact provenance.
- Existing ANSYS binary Result Intelligence compatibility.

## Tests added

`tests/python/test_ansys_v2_analysis.py` locks:

- admitted exact bundle + exact artifact;
- bundle fingerprint mismatch;
- post-reference artifact tamper;
- time-step mismatch;
- excitation component mismatch;
- unsupported result request;
- unrestrained reaction request;
- existing damping conflict;
- NONE damping control semantics;
- deterministic staged control injection;
- generic adapter preflight;
- external `loadPath` rejection in V2 mode;
- staged real-run provenance and source immutability;
- generic Python bridge transport;
- Result Intelligence compatibility with a real packaged ANSYS result fixture.

`tests/ts/engineering-tools.test.ts` locks:

- typed `FemSolverOptions.ansysV2` transport;
- no new ANSYS-specific LLM-visible execution tool;
- bundle-fingerprint / semantic-equivalence guidance presence.

## Fresh verification

The standard repository verification completed successfully:

- Typecheck — PASS
- TypeScript engineering bridge tests — PASS
- Python engineering core tests — PASS
- Ruff — PASS
- OpenSees adapter availability smoke — PASS
- ANSYS result reader import smoke — PASS
- FEM health smoke — PASS

The commands exercised by CI are:

```bash
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
python -c "from fem_core.solvers import get_solver_adapter; s=get_solver_adapter('opensees').status(); assert 'available' in s"
python -c "from ansys.mapdl import reader; assert callable(reader.read_binary)"
pnpm fem:health
```

PR29-focused acceptance tests are included in the full Python/TypeScript suites and can also be run directly:

```bash
python -m pytest tests/python/test_ansys_v2_analysis.py -q
pnpm exec tsx --test tests/ts/engineering-tools.test.ts
```

These checks are green on CI #633. A final documentation-only head CI must remain green before the PR is marked Ready for Review.

## Known intentional limitation

PR29 does **not** machine-prove that an arbitrary APDL bundle is semantically equivalent to the EngineeringModelSpec fingerprint carried by AnalysisSpec. It binds execution to exact APDL bytes and records `targetIdPolicy=IDENTITY` plus `semanticEquivalence=NOT_MACHINE_PROVEN`. A future deterministic ModelSpec→ANSYS renderer or explicit mapping artifact is required to remove this limitation.
