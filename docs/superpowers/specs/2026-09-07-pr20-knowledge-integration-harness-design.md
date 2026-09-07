# PR20 — Knowledge Integration Harness Design

Date: 2026-09-07
Status: Proposed design approved in chat; written-spec review required before implementation
Base: current `main` after PR15 Structural Response Intelligence V1
Branch: `feat/pr20-knowledge-integration-harness`
Roadmap label: `PR20` (GitHub's actual PR number may be the next available repository number because PR16–PR19 have not been opened in this repository)

## 1. Goal

PR20 establishes a deterministic, fixture-backed integration harness proving that FEMagent can consume normalized engineering knowledge evidence alongside existing FEM Engineering Evidence without making RAGFlow maturity a prerequisite for the FEMagent roadmap.

The PR validates this integration boundary:

```text
Pi Agent / Knowledge Tool
        |
        v
Knowledge Client contract
        |
        +-- FIXTURE provider (PR20, deterministic CI path)
        |
        +-- future RAGFlow provider (not implemented in PR20)
        |
        v
Normalized KnowledgeSearchResult
        |
        v
KnowledgeEvidence
        |
        +-----------------------------+
                                      |
Existing FEM tool path                |
        |                             |
        v                             |
EngineeringEvidence -----------------+
        |
        v
UnifiedEvidenceBundle
```

PR20 proves integration shape and evidence composition. It does **not** claim that the user's current RAG repository has production-grade retrieval quality.

## 2. Current repository boundary

Current `main` already contains:

- Pi Agent runtime and TypeScript/Python Engineering Tool Bridge;
- Model Intelligence and Model Bundle fingerprints;
- Load Intelligence and canonical load contracts;
- OpenSeesPy and ANSYS MAPDL SolverAdapters;
- Result Intelligence and Structural Response Intelligence;
- Engineering Evidence;
- explicit Engineering Semantic Roles;
- Cross-Solver Validation.

Current `main` does **not** contain:

- a Knowledge Intelligence package;
- a Knowledge Gateway client;
- `engiknow_search`;
- `KnowledgeEvidence`;
- a unified Knowledge + Engineering evidence contract;
- a production RAGFlow integration.

The separate `rag` repository is still under active retrieval/chunking/reranking evaluation. PR20 must therefore avoid coupling FEMagent CI or runtime correctness to that repository's current retrieval quality.

## 3. Scope decision

Roadmap PR16–PR19 were originally intended to land Knowledge contracts, Gateway, tools, and Unified Evidence before PR20. They have not yet been implemented in the FEMagent repository.

PR20 will **not** create fake empty PRs to preserve numbering and will **not** silently import the entire future production Knowledge stack.

Instead, PR20 will land one deliberately thin vertical slice containing only the durable contracts required by the harness:

1. a solver-independent `@femagent/knowledge-client` package;
2. canonical Knowledge search/evidence types;
3. a provider interface;
4. a deterministic local fixture provider used only when explicitly configured;
5. a SAFE `engiknow_search` Pi tool that fails closed when no provider is configured;
6. a minimal Unified Evidence composer reusing existing `FemEngineeringEvidence` objects unchanged;
7. fixture-backed integration tests proving Knowledge Evidence + Engineering Evidence coexist without changing Engineering Evidence truth semantics.

Future production RAGFlow work should implement the same provider interface rather than changing the Agent contract.

## 4. Non-goals

PR20 explicitly does **not** add:

- direct RAGFlow HTTP calls;
- RAGFlow deployment or Docker orchestration;
- embedding model configuration;
- reranker configuration;
- query rewrite;
- GraphRAG;
- multi-KB routing;
- production retrieval evaluation;
- claims about Recall@K or citation accuracy;
- any solver execution changes;
- any modification of `fem_core` engineering truth;
- any ability for knowledge text to override model/load/result/evidence facts;
- automatic engineering decisions based solely on retrieved text;
- Web UI;
- report generation.

## 5. Design principles

### 5.1 Knowledge guides; FEM evidence proves numerical truth

Knowledge retrieval may support methodology, assumptions, terminology, workflow suggestions, or references. It must never become the source of exact FEM numerical response values that belong to Result Intelligence / Engineering Evidence.

Example:

```text
KnowledgeEvidence:
"Transient time-step guidance recommends resolving the excitation and structural periods..."

EngineeringEvidence:
"Recorded run X, artifact Y, role TOWER_BASE_LEFT, displacement absolutePeak = ..."
```

These evidence classes are complementary and remain distinguishable.

### 5.2 Provider isolation

The Agent must consume a stable Knowledge Client contract, not RAGFlow-specific response JSON.

```text
engiknow_search
      |
      v
KnowledgeProvider.search(request)
      |
      +-- FixtureKnowledgeProvider   # PR20
      +-- RagflowKnowledgeProvider   # future
      +-- other retriever            # future
```

Provider internals may change without changing Pi tool parameters or `KnowledgeEvidence` semantics.

### 5.3 Fail closed by default

Normal FEMagent runtime must not silently return test fixtures.

Fixture retrieval is enabled only by explicit configuration:

```text
ENGIKNOW_KNOWLEDGE_MODE=fixture
ENGIKNOW_KNOWLEDGE_FIXTURE=<workspace-relative JSON path>
```

If no provider is configured, `engiknow_search` returns a stable `KNOWLEDGE_PROVIDER_NOT_CONFIGURED` error.

Unknown modes, missing fixture files, invalid schemas, paths escaping the active workspace, or malformed fixture content fail closed.

### 5.4 Fixture mode is evidence of integration, not evidence of retrieval quality

Fixture chunks are deterministic test inputs. Their retrieval scores and source metadata are synthetic/fixture-backed and must carry provenance showing that they came from `FIXTURE` mode.

Neither docs nor tests may describe fixture retrieval as successful RAGFlow retrieval.

### 5.5 Engineering Evidence remains unchanged

PR20 must reuse existing `FemEngineeringEvidence` and `FemEngineeringEvidenceReport` contracts. It must not fork, wrap, reinterpret, re-hash, or re-promote Engineering Evidence.

Unified composition is aggregation only.

## 6. Canonical Knowledge contract

Create package:

```text
packages/knowledge-client/
```

Logical request:

```ts
export interface KnowledgeSearchRequest {
  query: string;
  topK?: number;
  knowledgeBases?: string[];
}
```

V1 limits:

- `query`: non-empty after trimming;
- `topK`: default 8, allowed 1–20;
- `knowledgeBases`: optional opaque logical KB IDs; fixture provider may filter only when the fixture declares them.

Normalized chunk:

```ts
export interface KnowledgeChunk {
  chunkId: string;
  documentId: string;
  title: string;
  section: string | null;
  page: number | null;
  content: string;
  source: string;
  retrievalScore: number | null;
  rerankScore: number | null;
  metadata: Record<string, unknown>;
}
```

Search result:

```ts
export interface KnowledgeSearchResult {
  queryId: string;
  provider: "FIXTURE" | "RAGFLOW";
  query: string;
  chunks: KnowledgeChunk[];
  retrieval: {
    strategy: string;
    embeddingModel: string | null;
    rerankerModel: string | null;
  };
}
```

PR20 runtime emits only `provider: "FIXTURE"`; `"RAGFLOW"` is reserved in the durable type for the future provider and must not be emitted without a real adapter.

## 7. Knowledge Evidence

Knowledge Evidence is citation-oriented and must preserve retrieval provenance.

```ts
export interface KnowledgeEvidence {
  evidenceId: string;
  status: "RETRIEVED" | "LIMITED";
  claim: string;
  chunk: {
    chunkId: string;
    documentId: string;
    title: string;
    section: string | null;
    page: number | null;
    source: string;
  };
  retrieval: {
    queryId: string;
    provider: "FIXTURE" | "RAGFLOW";
    retrievalScore: number | null;
    rerankScore: number | null;
    strategy: string;
  };
}
```

`RETRIEVED` means the normalized provider returned the exact chunk represented by the evidence record. It does **not** mean the engineering statement is universally correct, current, or sufficient for design acceptance.

PR20 must not reuse Engineering Evidence's `VERIFIED` status for retrieved knowledge because the trust semantics differ.

## 8. Fixture provider

Fixture file schema:

```json
{
  "schema": "FEMAGENT_KNOWLEDGE_FIXTURE_V1",
  "provider": "FIXTURE",
  "retrieval": {
    "strategy": "fixture_exact",
    "embeddingModel": null,
    "rerankerModel": null
  },
  "queries": [
    {
      "match": "seismic time history",
      "chunks": [
        {
          "chunkId": "chunk-seismic-001",
          "documentId": "doc-sop-001",
          "title": "Seismic Time-History Analysis SOP",
          "section": "Time Step",
          "page": 4,
          "content": "Fixture content used to validate the integration contract.",
          "source": "fixture://seismic-sop",
          "retrievalScore": 0.98,
          "rerankScore": null,
          "metadata": {"knowledgeBase": "fea"}
        }
      ]
    }
  ]
}
```

Matching is deterministic and intentionally simple for PR20: normalized case-insensitive exact `match` against the trimmed query. It is not a search algorithm benchmark.

The provider:

- reads only the explicitly configured workspace-relative JSON file;
- rejects paths escaping the active workspace;
- validates schema exactly;
- does not fetch network resources;
- does not mutate the fixture;
- returns deterministic chunk ordering;
- clamps output to `topK`;
- generates stable `queryId` from provider mode + normalized request + fixture file SHA256.

## 9. Pi tool

Register a SAFE read-only tool in:

```text
.pi/extensions/knowledge-tools.ts
```

Tool name:

```text
engiknow_search
```

Parameters:

```text
query
optional topK
optional knowledgeBases
```

Prompt rules must state:

- retrieved knowledge is guidance/citation evidence, not solver truth;
- do not report fixture mode as real RAGFlow retrieval;
- do not invent missing page/section/scores;
- use FEM tools for model, load, solver, and numerical-response truth;
- a provider error must be surfaced rather than replaced with an LLM-authored answer pretending retrieval succeeded.

The tool has no solver execution permission and performs no workspace writes.

## 10. Unified Evidence Bundle

Create a minimal aggregation contract in `@femagent/knowledge-client`:

```ts
export interface UnifiedEvidenceBundle {
  schema: "FEMAGENT_UNIFIED_EVIDENCE_V1";
  projectId: string;
  knowledgeEvidence: KnowledgeEvidence[];
  engineeringEvidence: FemEngineeringEvidence[];
  limitations: Array<{
    source: "KNOWLEDGE" | "ENGINEERING";
    code: string;
    message: string;
  }>;
}
```

Composition helper:

```ts
composeUnifiedEvidenceBundle({
  projectId,
  knowledgeEvidence,
  engineeringReport,
}): UnifiedEvidenceBundle
```

Rules:

- include only `engineeringReport.verifiedEvidence` in `engineeringEvidence`;
- preserve every `FemEngineeringEvidence` object byte-for-structure unchanged;
- translate existing Engineering Evidence limitations only into bundle-level limitation references; do not alter their original statuses;
- do not promote Knowledge Evidence into Engineering Evidence;
- do not calculate engineering claims;
- deterministic ordering: knowledge input order, then engineering report order.

## 11. Integration harness

PR20's Golden Path is fixture-backed and must not require RAGFlow or licensed ANSYS.

Preferred deterministic test path:

```text
fixture knowledge search
        |
        v
KnowledgeEvidence
        |
        +--------------------------+
                                   |
existing recorded OpenSees fixture|
        |                          |
        v                          |
production Result Intelligence     |
        v                          |
production Engineering Evidence ---+
        |
        v
UnifiedEvidenceBundle
```

The engineering side must use the existing production Result Intelligence -> Engineering Evidence path rather than hard-coded numerical evidence objects wherever the existing test fixtures allow it.

The test proves:

1. fixture knowledge search returns normalized chunks;
2. Knowledge Evidence preserves exact citation/retrieval metadata;
3. existing Engineering Evidence is independently verified;
4. the unified bundle contains both evidence classes;
5. a knowledge chunk cannot change a FEM metric, artifact hash, status, unit, target, or provenance;
6. malformed fixture retrieval fails without affecting FEM evidence integrity;
7. CI needs neither RAGFlow nor ANSYS.

## 12. Error contract

Stable errors for PR20:

```text
KNOWLEDGE_PROVIDER_NOT_CONFIGURED
KNOWLEDGE_PROVIDER_MODE_UNSUPPORTED
KNOWLEDGE_FIXTURE_PATH_OUTSIDE_WORKSPACE
KNOWLEDGE_FIXTURE_NOT_FOUND
INVALID_KNOWLEDGE_FIXTURE
INVALID_KNOWLEDGE_QUERY
```

A valid fixture query with no matching configured query returns a successful result with `chunks: []`; it is not an exception.

## 13. Proposed files

Create:

```text
packages/knowledge-client/package.json
packages/knowledge-client/tsconfig.json
packages/knowledge-client/src/types.ts
packages/knowledge-client/src/provider.ts
packages/knowledge-client/src/fixtureProvider.ts
packages/knowledge-client/src/evidence.ts
packages/knowledge-client/src/index.ts
.pi/extensions/knowledge-tools.ts
tests/ts/knowledge-client.test.ts
tests/ts/knowledge-integration-harness.test.ts
tests/fixtures/knowledge/seismic-time-history.json
docs/architecture/knowledge-integration-harness.md
docs/verification/pr20-knowledge-integration-harness.md
```

Modify only as required for workspace/package/test registration:

```text
package.json
pnpm-lock.yaml
```

No `fem_core` Python files should change in PR20 unless an existing test harness cannot exercise production Engineering Evidence without a very small bridge fixture adjustment. Any such change must be justified before implementation rather than assumed by this spec.

## 14. Testing strategy

PR20 follows TDD.

Required focused tests:

- valid fixture schema loads deterministically;
- fixture path is workspace-confined;
- unknown mode fails closed;
- missing configuration fails closed;
- invalid query fails;
- no-match returns empty chunks;
- `topK` is enforced;
- stable query IDs change when query or fixture SHA changes;
- Knowledge Evidence preserves citation fields;
- Unified Evidence preserves existing `FemEngineeringEvidence` objects unchanged;
- Knowledge Evidence cannot be passed as Engineering Evidence;
- fixture-backed end-to-end harness composes real production Engineering Evidence with fixture Knowledge Evidence.

Required repository gate:

```text
pnpm typecheck
pnpm test:ts
python -m pytest
python -m ruff check fem_core tests/python examples/ansys/golden_path
pnpm fem:health
```

Existing OpenSees and ANSYS reader smoke checks in CI must remain green.

## 15. Acceptance criteria

PR20 is complete only when:

1. `@femagent/knowledge-client` exists with the canonical contract and provider boundary;
2. fixture mode is explicit and disabled by default;
3. `engiknow_search` is SAFE/read-only and fails closed without configuration;
4. fixture-backed retrieval is clearly identified as `FIXTURE` everywhere;
5. a deterministic test composes Knowledge Evidence and production Engineering Evidence into `FEMAGENT_UNIFIED_EVIDENCE_V1`;
6. no knowledge text can mutate or promote FEM numerical evidence;
7. no RAGFlow service is required for CI;
8. documentation states that PR20 proves integration readiness, not RAG retrieval quality;
9. full repository CI remains green.

## 16. Future handoff

After the user's RAG project reaches acceptable retrieval quality, a later production Knowledge Gateway/RAGFlow PR should:

```text
RagflowKnowledgeProvider
implements KnowledgeProvider
```

and map real RAGFlow responses into the same `KnowledgeSearchResult` contract.

That future PR may add health checks, authentication/configuration, retrieval trace normalization, and real evaluation. It must not require changes to:

- `engiknow_search` public semantics;
- Knowledge Evidence semantics;
- Unified Evidence semantics;
- FEM Engineering Evidence truth paths.

This separation allows FEMagent Model Authoring work to proceed while the RAG repository continues independent retrieval tuning.