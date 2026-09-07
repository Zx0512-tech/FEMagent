# PR20 Knowledge Integration Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic fixture-backed Knowledge Integration Harness that exposes a stable KnowledgeProvider contract, a SAFE `engiknow_search` Pi tool, Knowledge Evidence, and a minimal unified Knowledge + Engineering evidence bundle without depending on RAGFlow maturity.

**Architecture:** Introduce a focused TypeScript workspace package `@femagent/knowledge-client` that owns knowledge contracts, provider selection, fixture retrieval, citation-oriented Knowledge Evidence, and evidence aggregation. Pi consumes that package through a read-only `engiknow_search` tool. The integration harness composes fixture Knowledge Evidence with production `runFemEvidenceProject()` output, preserving Engineering Evidence objects unchanged.

**Tech Stack:** Node.js 22+, TypeScript 5.9, pnpm workspaces, Pi extension API, existing `@femagent/fem-tools`, Node test runner via `tsx --test`, GitHub Actions, Python 3.13 regression suite.

**Spec:** `docs/superpowers/specs/2026-09-07-pr20-knowledge-integration-harness-design.md`

## Global Constraints

- PR20 must not call RAGFlow or any network retrieval service.
- Fixture mode is disabled unless `ENGIKNOW_KNOWLEDGE_MODE=fixture` is explicitly set.
- Fixture path must be workspace-relative and must remain inside `ctx.cwd` / the active workspace.
- Stable errors are `KNOWLEDGE_PROVIDER_NOT_CONFIGURED`, `KNOWLEDGE_PROVIDER_MODE_UNSUPPORTED`, `KNOWLEDGE_FIXTURE_PATH_OUTSIDE_WORKSPACE`, `KNOWLEDGE_FIXTURE_NOT_FOUND`, `INVALID_KNOWLEDGE_FIXTURE`, and `INVALID_KNOWLEDGE_QUERY`.
- Query text must be non-empty after trimming; `topK` defaults to 8 and is limited to 1–20.
- PR20 runtime emits only `provider: "FIXTURE"`; `"RAGFLOW"` is reserved for a future adapter.
- Fixture matching is deterministic case-insensitive equality between trimmed query and configured `match`; this is not a retrieval benchmark.
- `KnowledgeEvidence.status` is `RETRIEVED | LIMITED`; it must never reuse Engineering Evidence `VERIFIED` semantics.
- `composeUnifiedEvidenceBundle()` includes only `engineeringReport.verifiedEvidence` and preserves those object values unchanged.
- Knowledge text must never mutate an engineering metric, unit, target, artifact hash, status, solver provenance, or case fingerprint.
- No `fem_core` production file changes are planned or permitted unless an unexpected blocker is proven first.
- CI must not require RAGFlow or licensed ANSYS.

---

### Task 1: RED — Knowledge Client Contract and Fixture Provider Tests

**Files:**
- Create: `tests/fixtures/knowledge/seismic-time-history.json`
- Create: `tests/ts/knowledge-client.test.ts`

**Interfaces tested before implementation:**
- `KnowledgeError` with stable `code`.
- `createConfiguredKnowledgeProvider(workspace, env)`.
- `FixtureKnowledgeProvider.search(request)`.
- `knowledgeEvidenceFromSearchResult(result)`.

- [ ] **Step 1: Add deterministic fixture**

Create a `FEMAGENT_KNOWLEDGE_FIXTURE_V1` file containing two chunks for the exact query `seismic time history`. One chunk must use `metadata.knowledgeBase = "fea"`. Include clearly synthetic fixture text and never claim the text came from RAGFlow.

- [ ] **Step 2: Add failing provider tests**

The tests must import from `@femagent/knowledge-client` before the package exists and cover:

```ts
await assert.rejects(
  () => createConfiguredKnowledgeProvider(cwd, {}),
  (error: unknown) => error instanceof KnowledgeError
    && error.code === "KNOWLEDGE_PROVIDER_NOT_CONFIGURED",
);
```

Also test unsupported mode, path escape, missing file, invalid query, valid exact match, no-match empty chunks, `topK`, KB filtering, stable query IDs, and citation field preservation.

- [ ] **Step 3: Commit RED tests only**

Commit message: `test: define PR20 knowledge client contract`

- [ ] **Step 4: Verify RED using PR GitHub Actions**

Expected failure: TypeScript typecheck/test collection cannot resolve `@femagent/knowledge-client` or its exported APIs. Record the failing run ID in the PR verification document later.

---

### Task 2: GREEN — Implement Knowledge Client and Fixture Provider

**Files:**
- Create: `packages/knowledge-client/package.json`
- Create: `packages/knowledge-client/tsconfig.json`
- Create: `packages/knowledge-client/src/types.ts`
- Create: `packages/knowledge-client/src/provider.ts`
- Create: `packages/knowledge-client/src/fixtureProvider.ts`
- Create: `packages/knowledge-client/src/index.ts`
- Modify: `package.json`

**Interfaces:**
- Produces `KnowledgeSearchRequest`, `KnowledgeChunk`, `KnowledgeSearchResult`, `KnowledgeEvidence` type shells.
- Produces `KnowledgeProvider`.
- Produces `KnowledgeError`.
- Produces `createConfiguredKnowledgeProvider(workspace: string, env?: NodeJS.ProcessEnv): Promise<KnowledgeProvider>`.
- Produces `FixtureKnowledgeProvider`.

- [ ] **Step 1: Add workspace package metadata**

`packages/knowledge-client/package.json`:

```json
{
  "name": "@femagent/knowledge-client",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "exports": { ".": "./src/index.ts" },
  "dependencies": { "@femagent/fem-tools": "workspace:*" },
  "engines": { "node": ">=22" }
}
```

Add `"@femagent/knowledge-client": "workspace:*"` to root dependencies so tests and `.pi` extensions resolve the package.

- [ ] **Step 2: Implement canonical types and error codes**

Define exact request/chunk/result/evidence types from the spec and a `KnowledgeError` class carrying one stable PR20 error code.

- [ ] **Step 3: Implement provider selection**

`createConfiguredKnowledgeProvider()` must reject missing mode, reject modes other than `fixture`, require `ENGIKNOW_KNOWLEDGE_FIXTURE`, and construct `FixtureKnowledgeProvider` without network access.

- [ ] **Step 4: Implement strict fixture loading and search**

The provider must reject absolute paths and workspace escapes, convert `ENOENT` to `KNOWLEDGE_FIXTURE_NOT_FOUND`, convert malformed JSON/schema/type errors to `INVALID_KNOWLEDGE_FIXTURE`, normalize query text, validate `topK`, use exact case-insensitive match, filter declared KB metadata when requested, preserve fixture chunk order, clamp to `topK`, and derive `queryId` from SHA256 of provider + normalized request + fixture SHA256.

- [ ] **Step 5: Run focused GREEN CI**

Expected: `pnpm typecheck` and `pnpm test:ts` pass the new provider tests; Python jobs remain unchanged.

- [ ] **Step 6: Commit**

Commit message: `feat: add fixture-backed knowledge provider`

---

### Task 3: RED — Unified Evidence and Golden-Path Tests

**Files:**
- Create: `tests/ts/knowledge-integration-harness.test.ts`

**Interfaces tested before implementation:**
- `knowledgeEvidenceFromSearchResult(result): KnowledgeEvidence[]`.
- `composeUnifiedEvidenceBundle({ projectId, knowledgeEvidence, engineeringReport }): UnifiedEvidenceBundle`.

- [ ] **Step 1: Add failing evidence composition tests**

Build a production Engineering Evidence report using the same recorded OpenSees-style run manifest/result artifacts used by `tests/ts/evidence-api.test.ts` and `runFemEvidenceProject()`.

Assert:

```ts
assert.equal(engineeringReport.verifiedEvidence[0]?.status, "VERIFIED");
assert.equal(engineeringReport.verifiedEvidence[0]?.metric.summary?.absolutePeak, 0.03);
```

Then search fixture knowledge, convert it into Knowledge Evidence, compose the bundle, and require schema `FEMAGENT_UNIFIED_EVIDENCE_V1`.

- [ ] **Step 2: Prove trust separation**

Before composition, deep-clone the Engineering Evidence object. After composition assert deep equality with the original. Fixture content may contain a deliberately conflicting number such as `9999`; engineering peak must remain `0.03` and engineering status must remain `VERIFIED`.

- [ ] **Step 3: Prove malformed knowledge does not alter engineering evidence**

After obtaining a valid Engineering Evidence report, point the fixture provider at malformed fixture JSON, assert `INVALID_KNOWLEDGE_FIXTURE`, and re-assert the engineering report remains unchanged.

- [ ] **Step 4: Commit RED test**

Commit message: `test: define unified knowledge and engineering evidence`

- [ ] **Step 5: Verify RED in GitHub Actions**

Expected failure: evidence composition exports are missing.

---

### Task 4: GREEN — Knowledge Evidence, Unified Evidence, and Pi Tool

**Files:**
- Create: `packages/knowledge-client/src/evidence.ts`
- Modify: `packages/knowledge-client/src/index.ts`
- Create: `.pi/extensions/knowledge-tools.ts`
- Modify: `apps/agent/src/main.ts`

**Interfaces:**
- `knowledgeEvidenceFromSearchResult()` produces one citation-oriented record per returned chunk.
- `composeUnifiedEvidenceBundle()` aggregates evidence without changing Engineering Evidence.
- `engiknow_search` is SAFE/read-only and returns normalized search result plus Knowledge Evidence.

- [ ] **Step 1: Implement Knowledge Evidence conversion**

Use deterministic IDs derived from query ID + chunk ID. Set `claim` to exact chunk content, `status` to `RETRIEVED`, and preserve title/section/page/source/retrieval scores exactly.

- [ ] **Step 2: Implement Unified Evidence composition**

Return:

```ts
{
  schema: "FEMAGENT_UNIFIED_EVIDENCE_V1",
  projectId,
  knowledgeEvidence,
  engineeringEvidence: engineeringReport.verifiedEvidence,
  limitations
}
```

Translate knowledge `LIMITED` records and Engineering Evidence report limitations into bundle-level limitation references without modifying their source objects.

- [ ] **Step 3: Implement SAFE `engiknow_search` Pi extension**

Register parameters `query`, optional `topK`, optional `knowledgeBases`; use `ctx.cwd` and `process.env`; surface provider errors; include prompt guidance that fixture mode is not RAGFlow retrieval and FEM numerical truth must come from FEM tools.

- [ ] **Step 4: Wire the tool into the SDK agent entrypoint**

Add `.pi/extensions/knowledge-tools.ts` to `additionalExtensionPaths` and `engiknow_search` to the explicit tool list in `apps/agent/src/main.ts`.

- [ ] **Step 5: Run GREEN CI**

Expected: TypeScript tests including the integration harness pass; Python suite, Ruff, OpenSees smoke, ANSYS reader smoke, and health smoke remain green.

- [ ] **Step 6: Commit**

Commit message: `feat: add knowledge evidence integration harness`

---

### Task 5: Architecture Documentation and Final Verification

**Files:**
- Create: `docs/architecture/knowledge-integration-harness.md`
- Create: `docs/verification/pr20-knowledge-integration-harness.md`
- Update: PR #16 body/status after exact-head validation.

**Interfaces:**
- Documentation must clearly separate fixture integration readiness from real RAG/RAGFlow retrieval quality.

- [ ] **Step 1: Document architecture and future adapter boundary**

State that future `RagflowKnowledgeProvider implements KnowledgeProvider` and must map into the existing contract without changing Engineering Evidence semantics.

- [ ] **Step 2: Record RED/GREEN run IDs and exact final head**

Verification doc must list the intentional RED runs, final GREEN run, test counts, and any pre-existing warnings.

- [ ] **Step 3: Run full exact-head repository gate**

The GitHub Actions workflow must execute and pass the equivalent of:

```text
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
pnpm fem:health
OpenSees adapter availability smoke
ANSYS result-reader import smoke
```

- [ ] **Step 4: Review PR diff against scope**

Confirm no RAGFlow/network code, no `fem_core` production changes, no solver execution changes, no unit/semantic inference, and no mutation/promotion of Engineering Evidence.

- [ ] **Step 5: Update PR #16 from Draft only after exact-head verification**

PR title remains roadmap label `PR20 — Knowledge Integration Harness`; body must disclose GitHub numeric PR #16 and explicitly state that the harness proves integration readiness, not retrieval quality.
