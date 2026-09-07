# Knowledge Integration Harness

## Purpose

PR20 adds the first knowledge boundary to FEMagent without making the unfinished RAG/RAGFlow project part of engineering truth or CI availability.

The harness proves that FEMagent can consume normalized knowledge evidence and combine it with independently verified FEM evidence while preserving the existing solver-owned numerical trust chain.

## Architecture

```text
Pi Agent
  |
  +-- engiknow_search (SAFE / read-only)
  |       |
  |       v
  |   KnowledgeProvider
  |       |
  |       +-- FixtureKnowledgeProvider   <- PR20 runtime
  |       +-- RagflowKnowledgeProvider   <- future adapter, not implemented
  |       |
  |       v
  |   KnowledgeSearchResult
  |       v
  |   KnowledgeEvidence
  |
  +-- existing FEM tools
          |
          v
      fem_core / solver artifacts
          v
      EngineeringEvidence

KnowledgeEvidence + EngineeringEvidence
              |
              v
  FEMAGENT_UNIFIED_EVIDENCE_V1
```

## Provider boundary

`@femagent/knowledge-client` owns the provider-neutral contract. A provider implements only:

```ts
interface KnowledgeProvider {
  search(request: KnowledgeSearchRequest): Promise<KnowledgeSearchResult>;
}
```

PR20 implements only `FixtureKnowledgeProvider`. It performs no network requests, embeddings, reranking, query rewriting, or RAGFlow API calls.

The fixture provider is enabled only when both variables are explicitly configured:

```text
ENGIKNOW_KNOWLEDGE_MODE=fixture
ENGIKNOW_KNOWLEDGE_FIXTURE=<workspace-relative-json-path>
```

Missing configuration fails closed. Absolute fixture paths and workspace escapes are rejected.

A future real adapter should implement:

```text
RagflowKnowledgeProvider implements KnowledgeProvider
```

and map RAGFlow responses into the existing `KnowledgeSearchResult` contract. That adapter must not change FEM Result Intelligence or Engineering Evidence semantics.

## Fixture semantics

Fixture retrieval is deliberately deterministic:

1. trim and normalize the query;
2. perform case-insensitive exact matching against fixture `match` values;
3. optionally filter chunks by explicit `metadata.knowledgeBase`;
4. preserve fixture ordering;
5. apply `topK` (default 8, allowed 1-20);
6. derive `queryId` from the normalized request and fixture SHA256.

This mechanism is an integration harness, not a retrieval-quality benchmark. A fixture result must never be presented as RAGFlow, embedding, or reranker output.

## Evidence separation

Knowledge evidence is citation-oriented and uses:

```text
RETRIEVED | LIMITED
```

Engineering evidence continues to use the existing FEM statuses:

```text
VERIFIED | INVALID | LIMITED | UNVERIFIED
```

`KnowledgeEvidence` cannot be promoted to `VERIFIED` Engineering Evidence.

`composeUnifiedEvidenceBundle()` includes only `engineeringReport.verifiedEvidence` on the engineering side and preserves those evidence objects unchanged. It does not calculate FEM values, infer units, alter targets, rewrite provenance, or change artifact hashes.

The integration test intentionally places a synthetic `9999` value in a knowledge fixture while the production Engineering Evidence path proves a displacement peak of `0.03`. The bundle must retain the FEM value and `VERIFIED` status unchanged.

## Pi tool

`.pi/extensions/knowledge-tools.ts` registers:

```text
engiknow_search
```

The tool is SAFE/read-only. It has no solver execution permission and performs no workspace writes.

Its prompt contract requires the Agent to:

- use retrieved knowledge as guidance/citation evidence;
- never describe fixture mode as live RAGFlow retrieval;
- preserve returned citation metadata;
- use FEM tools and solver artifacts for numerical engineering truth;
- surface provider errors instead of pretending retrieval succeeded.

## Error contract

PR20 exposes stable knowledge errors:

```text
KNOWLEDGE_PROVIDER_NOT_CONFIGURED
KNOWLEDGE_PROVIDER_MODE_UNSUPPORTED
KNOWLEDGE_FIXTURE_PATH_OUTSIDE_WORKSPACE
KNOWLEDGE_FIXTURE_NOT_FOUND
INVALID_KNOWLEDGE_FIXTURE
INVALID_KNOWLEDGE_QUERY
```

A valid query with no fixture match succeeds with `chunks: []`.

## What PR20 proves

PR20 proves the integration boundary:

```text
KnowledgeProvider -> KnowledgeEvidence
                    +
production Result Intelligence -> EngineeringEvidence
                    -> UnifiedEvidenceBundle
```

It does **not** prove RAG retrieval quality, Recall@K, citation accuracy against a live corpus, reranker quality, query-rewrite quality, or production RAGFlow availability. Those remain responsibilities of the separate RAG project and a later real-provider integration PR.
