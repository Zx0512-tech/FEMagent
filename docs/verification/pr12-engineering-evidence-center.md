# PR12 Validation — Engineering Evidence Center V1

## Status

PR12 implementation and closeout documentation are present on the feature branch. The pull request must remain Draft until the exact final documentation head passes the full repository CI gate and the final base/diff review is repeated.

## What PR12 proves

PR12 introduces the first deterministic evidence layer downstream of Result Intelligence:

```text
completed solver run
  -> run_manifest + recorded result artifact
  -> inspect_result() integrity verification
  -> query_result() deterministic metric
  -> EngineeringEvidence projection
  -> Engineering Report projection
  -> evidence.project bridge command
  -> runFemEvidenceProject()
  -> fem_evidence_project SAFE Pi tool
```

The evidence layer does not execute a solver and does not create numerical truth independently of recorded solver artifacts.

## Evidence status contract

| Status | V1 meaning |
| --- | --- |
| `VERIFIED` | Production run-backed projection has an artifact reference and SHA supplied only after Result Intelligence reports that result artifact as verified. |
| `LIMITED` | Artifact reference exists but no verified digest is available. |
| `UNVERIFIED` | No auditable artifact reference is available. |
| `INVALID` | Artifact reference itself is malformed. |

Low-level `project_claim()` / `validate_evidence()` are pure projection primitives and do not perform filesystem integrity checks. The production Agent/Bridge route uses `project_run_evidence()`, which first calls production `inspect_result()` and preserves Result Intelligence integrity failures.

## TDD evidence

Task 4 preserved explicit RED -> GREEN evidence.

### Python API RED

GitHub Actions CI **#185** failed during Python collection because `fem_core.evidence.api` did not yet exist. Existing TypeScript bridge tests remained green.

### Python API GREEN

After implementing the read-only run-backed API, CI **#189** reached **102 passing Python tests**. The only remaining failures were four mechanical Ruff import/order findings; no functional test failed. Those lint findings were corrected without changing Evidence API behavior.

The Python regression tests prove:

- a valid recorded OpenSees result can become `VERIFIED` evidence;
- evidence carries node/component entity identity, metric, run ID, solver, and case fingerprint;
- tampering with `response.csv` after the manifest is written causes `RESULT_ARTIFACT_HASH_MISMATCH`;
- the integrity error is preserved rather than downgraded into a limitation or replaced by a fabricated claim.

### TypeScript Bridge RED

CI **#194** failed at typecheck because `runFemEvidenceProject` was intentionally referenced by the new test before the function existed.

### Task 4 GREEN

CI **#199** validated implementation head `b3e6aad97245bcac4460bd6e8a468cde38dad2c0`:

- `pnpm typecheck` — PASS;
- `pnpm test:ts` — **13/13 PASS**;
- `python -m pytest` — **102/102 PASS**;
- Ruff — PASS;
- OpenSees adapter availability smoke — PASS;
- ANSYS result-reader import smoke — PASS;
- `pnpm fem:health` — PASS.

Python emitted 66 existing third-party VTK/NumPy deprecation warnings from ANSYS result-reading paths; there were no test or lint failures.

## Regression acceptance matrix

| Requirement | Verification |
| --- | --- |
| Evidence has explicit status | Unit tests cover `VERIFIED`, `LIMITED`, and `UNVERIFIED` promotion behavior. |
| Unsupported free text cannot become run-backed verified evidence | Production API derives the claim from a Result Intelligence payload and requires an artifact selected from inspected run integrity data. |
| Result artifact integrity is checked before promotion | `project_run_evidence()` calls `inspect_result()` before `query_result()` and only uses SHA from an artifact with Result Intelligence status `VERIFIED`. |
| Tamper detection is fail-closed | API regression mutates `response.csv` and requires `RESULT_ARTIFACT_HASH_MISMATCH`. |
| Run provenance is retained | API regression asserts `runId`, `caseFingerprint`, and solver in evidence/report output. |
| Deterministic target identity is retained | Evidence entity contains the Result Intelligence node ID and normalized component. |
| Semantic structural role is not invented | Pi tool requires an already-resolved node target and explicitly prohibits role-to-node guessing. |
| Unknown units are not invented | Metric unit is copied from Result Intelligence; `null` remains `null`. |
| Non-verified evidence is separated | Engineering Report emits only `VERIFIED` entries under `verifiedEvidence`; all other statuses remain under `limitations`. |
| API is read-only | Production API uses Result Intelligence inspect/query and has no solver adapter run call. |
| Existing bridge architecture is reused | Python command `evidence.project`, TypeScript `runFemEvidenceProject()`, and Pi `fem_evidence_project` use the existing strict bridge rather than a new HTTP service. |

## Base synchronization during closeout

PR12 originally branched from PR10 merge commit `addcfec2af71f1d5d545ca608daa3c75e6581d09`.

At final closeout, repository comparison showed the feature branch was **18 commits behind** current `main` (`b3bce431c1067301ba26e76e13bac769fe628a4b`) while remaining conflict-free.

Before writing final PR12 documentation, current `main` was merged into the feature branch using merge commit:

```text
60a21e1bd94ad63a4bb488024e7f14ef7a0f89f3
```

Its parents are:

```text
b3bce431c1067301ba26e76e13bac769fe628a4b  current main
b3e6aad97245bcac4460bd6e8a468cde38dad2c0  PR12 implementation head
```

This ensures final verification is performed on the current repository baseline rather than the stale PR10 base.

## Engineering diff review

The PR12 feature diff is reviewed against these boundaries:

- **Solver execution:** none added to the evidence path. `fem_evidence_project` remains SAFE/read-only.
- **Artifact integrity bypass:** the production API does not accept a caller-supplied result SHA; it obtains artifact integrity from `inspect_result()`.
- **Integrity failure suppression:** none. Result Intelligence domain errors, including hash mismatch, propagate.
- **Unit guessing:** none. Evidence preserves Result Intelligence units and does not reinterpret ANSYS solver-native values as SI.
- **Semantic-role guessing:** none. Node/component identity is retained, but structural roles remain out of scope.
- **Second result parser/store:** none. Evidence references existing recorded artifacts and Result Intelligence payloads.
- **Parallel HTTP stack:** none. Existing Python/TypeScript/Pi bridge architecture is extended.
- **LLM-authored engineering conclusion:** none. V1 claim text is deterministic and generic (`Recorded <quantity> engineering response`).
- **Report promotion leak:** none. Non-`VERIFIED` evidence is retained only as a limitation.

One deliberate architectural distinction is documented: the pure low-level projection primitive validates evidence structure but does not itself perform I/O/hash verification. Production run-backed verification is supplied by Result Intelligence before projection.

## Review-thread state at closeout start

Before final documentation was added:

- open inline review threads: **0**;
- submitted PR reviews: **0**;
- PR conversation comments: **0**.

These counts must be checked again before the Draft flag is removed.

## Full repository gate

The exact final PR12 head must pass the same repository gate used by current `main`:

```text
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
OpenSees adapter availability smoke
ANSYS result-reader import smoke
pnpm fem:health
```

## Final Ready-for-review criterion

PR12 may be marked **Ready for review** only when all of the following are true on the exact final head:

1. the branch contains current `main` with no unresolved merge conflict;
2. architecture and verification documentation are committed;
3. full PR diff has no unresolved blocker from final engineering review;
4. PR review threads/comments contain no unresolved required change;
5. full GitHub Actions CI is successful on the exact final head;
6. PR metadata accurately describes the implemented scope and verification result.

Ready-for-review is not merge approval. PR12 remains open for the user's explicit merge decision.
