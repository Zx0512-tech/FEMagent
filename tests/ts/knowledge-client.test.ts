import assert from "node:assert/strict";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import {
  KnowledgeError,
  createConfiguredKnowledgeProvider,
  knowledgeEvidenceFromSearchResult,
} from "@femagent/knowledge-client";

const cwd = process.cwd();
const fixturePath = "tests/fixtures/knowledge/seismic-time-history.json";

function fixtureEnv(overrides: NodeJS.ProcessEnv = {}): NodeJS.ProcessEnv {
  return {
    ENGIKNOW_KNOWLEDGE_MODE: "fixture",
    ENGIKNOW_KNOWLEDGE_FIXTURE: fixturePath,
    ...overrides,
  };
}

function hasCode(code: string) {
  return (error: unknown): boolean => error instanceof KnowledgeError && error.code === code;
}

test("knowledge provider fails closed when configuration is missing", async () => {
  await assert.rejects(
    () => createConfiguredKnowledgeProvider(cwd, {}),
    hasCode("KNOWLEDGE_PROVIDER_NOT_CONFIGURED"),
  );
});

test("knowledge provider rejects unsupported modes", async () => {
  await assert.rejects(
    () => createConfiguredKnowledgeProvider(cwd, { ENGIKNOW_KNOWLEDGE_MODE: "ragflow" }),
    hasCode("KNOWLEDGE_PROVIDER_MODE_UNSUPPORTED"),
  );
});

test("fixture provider rejects paths outside the active workspace", async () => {
  await assert.rejects(
    () => createConfiguredKnowledgeProvider(cwd, fixtureEnv({ ENGIKNOW_KNOWLEDGE_FIXTURE: "../outside.json" })),
    hasCode("KNOWLEDGE_FIXTURE_PATH_OUTSIDE_WORKSPACE"),
  );
});

test("fixture provider reports missing fixture files with a stable code", async () => {
  const provider = await createConfiguredKnowledgeProvider(
    cwd,
    fixtureEnv({ ENGIKNOW_KNOWLEDGE_FIXTURE: "tests/fixtures/knowledge/missing.json" }),
  );
  await assert.rejects(
    () => provider.search({ query: "seismic time history" }),
    hasCode("KNOWLEDGE_FIXTURE_NOT_FOUND"),
  );
});

test("fixture provider rejects empty queries and invalid topK", async () => {
  const provider = await createConfiguredKnowledgeProvider(cwd, fixtureEnv());
  await assert.rejects(() => provider.search({ query: "   " }), hasCode("INVALID_KNOWLEDGE_QUERY"));
  await assert.rejects(
    () => provider.search({ query: "seismic time history", topK: 0 }),
    hasCode("INVALID_KNOWLEDGE_QUERY"),
  );
  await assert.rejects(
    () => provider.search({ query: "seismic time history", topK: 21 }),
    hasCode("INVALID_KNOWLEDGE_QUERY"),
  );
});

test("fixture search is deterministic, exact, case-insensitive, and bounded by topK", async () => {
  const provider = await createConfiguredKnowledgeProvider(cwd, fixtureEnv());
  const first = await provider.search({ query: " seismic time history ", topK: 1 });
  const second = await provider.search({ query: "SEISMIC TIME HISTORY", topK: 1 });

  assert.equal(first.provider, "FIXTURE");
  assert.equal(first.query, "seismic time history");
  assert.equal(first.retrieval.strategy, "fixture_exact");
  assert.equal(first.retrieval.embeddingModel, null);
  assert.equal(first.retrieval.rerankerModel, null);
  assert.equal(first.chunks.length, 1);
  assert.equal(first.chunks[0]?.chunkId, "chunk-seismic-001");
  assert.equal(first.queryId, second.queryId);

  const two = await provider.search({ query: "seismic time history", topK: 2 });
  assert.equal(two.chunks.length, 2);
  assert.notEqual(two.queryId, first.queryId);
});

test("valid fixture query with no exact match returns an empty result", async () => {
  const provider = await createConfiguredKnowledgeProvider(cwd, fixtureEnv());
  const result = await provider.search({ query: "modal damping guidance" });
  assert.equal(result.provider, "FIXTURE");
  assert.deepEqual(result.chunks, []);
});

test("fixture provider filters only declared knowledge base metadata", async () => {
  const provider = await createConfiguredKnowledgeProvider(cwd, fixtureEnv());
  const result = await provider.search({
    query: "seismic time history",
    topK: 8,
    knowledgeBases: ["fea"],
  });
  assert.deepEqual(result.chunks.map((chunk) => chunk.chunkId), ["chunk-seismic-001"]);
});

test("Knowledge Evidence preserves citation and retrieval provenance", async () => {
  const provider = await createConfiguredKnowledgeProvider(cwd, fixtureEnv());
  const result = await provider.search({ query: "seismic time history", topK: 1 });
  const evidence = knowledgeEvidenceFromSearchResult(result);

  assert.equal(evidence.length, 1);
  assert.equal(evidence[0]?.status, "RETRIEVED");
  assert.equal(evidence[0]?.claim, result.chunks[0]?.content);
  assert.deepEqual(evidence[0]?.chunk, {
    chunkId: "chunk-seismic-001",
    documentId: "doc-sop-001",
    title: "Seismic Time-History Analysis Fixture",
    section: "Time Step",
    page: 4,
    source: "fixture://seismic-sop",
  });
  assert.equal(evidence[0]?.retrieval.provider, "FIXTURE");
  assert.equal(evidence[0]?.retrieval.retrievalScore, 0.98);
  assert.equal(evidence[0]?.retrieval.rerankScore, null);
  assert.equal(evidence[0]?.retrieval.strategy, "fixture_exact");
});

test("queryId changes when the fixture content digest changes", async () => {
  const tempDir = path.join(cwd, ".femagent", "test-knowledge-client");
  const relativeFixture = path.posix.join(".femagent", "test-knowledge-client", "fixture.json");
  await mkdir(tempDir, { recursive: true });
  try {
    const base = {
      schema: "FEMAGENT_KNOWLEDGE_FIXTURE_V1",
      provider: "FIXTURE",
      retrieval: { strategy: "fixture_exact", embeddingModel: null, rerankerModel: null },
      queries: [{
        match: "digest test",
        chunks: [{
          chunkId: "c1",
          documentId: "d1",
          title: "Digest Fixture",
          section: null,
          page: null,
          content: "version one",
          source: "fixture://digest",
          retrievalScore: null,
          rerankScore: null,
          metadata: {},
        }],
      }],
    };
    await writeFile(path.join(tempDir, "fixture.json"), JSON.stringify(base), "utf8");
    const provider1 = await createConfiguredKnowledgeProvider(cwd, fixtureEnv({ ENGIKNOW_KNOWLEDGE_FIXTURE: relativeFixture }));
    const result1 = await provider1.search({ query: "digest test" });

    base.queries[0]!.chunks[0]!.content = "version two";
    await writeFile(path.join(tempDir, "fixture.json"), JSON.stringify(base), "utf8");
    const provider2 = await createConfiguredKnowledgeProvider(cwd, fixtureEnv({ ENGIKNOW_KNOWLEDGE_FIXTURE: relativeFixture }));
    const result2 = await provider2.search({ query: "digest test" });

    assert.notEqual(result1.queryId, result2.queryId);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});
