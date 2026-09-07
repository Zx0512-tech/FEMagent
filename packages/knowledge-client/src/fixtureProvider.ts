import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

import {
  KnowledgeError,
  normalizeKnowledgeSearchRequest,
  type KnowledgeProvider,
} from "./provider.js";
import type { KnowledgeChunk, KnowledgeSearchRequest, KnowledgeSearchResult } from "./types.js";

interface KnowledgeFixture {
  schema: "FEMAGENT_KNOWLEDGE_FIXTURE_V1";
  provider: "FIXTURE";
  retrieval: {
    strategy: string;
    embeddingModel: string | null;
    rerankerModel: string | null;
  };
  queries: Array<{
    match: string;
    chunks: KnowledgeChunk[];
  }>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function invalidFixture(message: string): never {
  throw new KnowledgeError("INVALID_KNOWLEDGE_FIXTURE", message);
}

function assertExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
  label: string,
): void {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    invalidFixture(`${label} must contain exactly: ${wanted.join(", ")}`);
  }
}

function nullableString(value: unknown, label: string): string | null {
  if (value === null) return null;
  if (typeof value !== "string") invalidFixture(`${label} must be a string or null`);
  return value;
}

function nullableScore(value: unknown, label: string): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    invalidFixture(`${label} must be a finite number or null`);
  }
  return value;
}

function requiredString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) {
    invalidFixture(`${label} must be a non-empty string`);
  }
  return value;
}

function parseChunk(value: unknown, label: string): KnowledgeChunk {
  if (!isRecord(value)) invalidFixture(`${label} must be an object`);
  assertExactKeys(
    value,
    [
      "chunkId",
      "documentId",
      "title",
      "section",
      "page",
      "content",
      "source",
      "retrievalScore",
      "rerankScore",
      "metadata",
    ],
    label,
  );

  const page = value.page;
  if (page !== null && (!Number.isInteger(page) || (page as number) < 1)) {
    invalidFixture(`${label}.page must be a positive integer or null`);
  }
  if (!isRecord(value.metadata)) invalidFixture(`${label}.metadata must be an object`);

  return {
    chunkId: requiredString(value.chunkId, `${label}.chunkId`),
    documentId: requiredString(value.documentId, `${label}.documentId`),
    title: requiredString(value.title, `${label}.title`),
    section: nullableString(value.section, `${label}.section`),
    page: page as number | null,
    content: requiredString(value.content, `${label}.content`),
    source: requiredString(value.source, `${label}.source`),
    retrievalScore: nullableScore(value.retrievalScore, `${label}.retrievalScore`),
    rerankScore: nullableScore(value.rerankScore, `${label}.rerankScore`),
    metadata: { ...value.metadata },
  };
}

function parseFixture(raw: string): KnowledgeFixture {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    invalidFixture("Knowledge fixture must contain valid JSON");
  }
  if (!isRecord(value)) invalidFixture("Knowledge fixture root must be an object");
  assertExactKeys(value, ["schema", "provider", "retrieval", "queries"], "Knowledge fixture root");
  if (value.schema !== "FEMAGENT_KNOWLEDGE_FIXTURE_V1") {
    invalidFixture("Knowledge fixture schema must be FEMAGENT_KNOWLEDGE_FIXTURE_V1");
  }
  if (value.provider !== "FIXTURE") invalidFixture("Knowledge fixture provider must be FIXTURE");
  if (!isRecord(value.retrieval)) invalidFixture("Knowledge fixture retrieval must be an object");
  assertExactKeys(
    value.retrieval,
    ["strategy", "embeddingModel", "rerankerModel"],
    "Knowledge fixture retrieval",
  );
  const retrieval = {
    strategy: requiredString(value.retrieval.strategy, "Knowledge fixture retrieval.strategy"),
    embeddingModel: nullableString(value.retrieval.embeddingModel, "Knowledge fixture retrieval.embeddingModel"),
    rerankerModel: nullableString(value.retrieval.rerankerModel, "Knowledge fixture retrieval.rerankerModel"),
  };
  if (!Array.isArray(value.queries)) invalidFixture("Knowledge fixture queries must be an array");

  const queries = value.queries.map((entry, queryIndex) => {
    const label = `Knowledge fixture queries[${queryIndex}]`;
    if (!isRecord(entry)) invalidFixture(`${label} must be an object`);
    assertExactKeys(entry, ["match", "chunks"], label);
    const match = requiredString(entry.match, `${label}.match`).trim().toLowerCase();
    if (!Array.isArray(entry.chunks)) invalidFixture(`${label}.chunks must be an array`);
    return {
      match,
      chunks: entry.chunks.map((chunk, chunkIndex) => parseChunk(chunk, `${label}.chunks[${chunkIndex}]`)),
    };
  });

  return {
    schema: "FEMAGENT_KNOWLEDGE_FIXTURE_V1",
    provider: "FIXTURE",
    retrieval,
    queries,
  };
}

function resolveFixturePath(workspace: string, configuredPath: string): string {
  const trimmed = configuredPath.trim();
  if (!trimmed || path.isAbsolute(trimmed)) {
    throw new KnowledgeError(
      "KNOWLEDGE_FIXTURE_PATH_OUTSIDE_WORKSPACE",
      "Knowledge fixture path must be a workspace-relative path",
    );
  }
  const root = path.resolve(workspace);
  const resolved = path.resolve(root, trimmed);
  const relative = path.relative(root, resolved);
  if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new KnowledgeError(
      "KNOWLEDGE_FIXTURE_PATH_OUTSIDE_WORKSPACE",
      "Knowledge fixture path escapes the active workspace",
    );
  }
  return resolved;
}

async function readFixture(fixturePath: string): Promise<{ fixture: KnowledgeFixture; sha256: string }> {
  let raw: string;
  try {
    raw = await readFile(fixturePath, "utf8");
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT") {
      throw new KnowledgeError("KNOWLEDGE_FIXTURE_NOT_FOUND", "Configured knowledge fixture file does not exist");
    }
    throw new KnowledgeError("INVALID_KNOWLEDGE_FIXTURE", `Unable to read knowledge fixture: ${String(error)}`);
  }
  const sha256 = createHash("sha256").update(raw).digest("hex");
  return { fixture: parseFixture(raw), sha256 };
}

export class FixtureKnowledgeProvider implements KnowledgeProvider {
  private readonly fixturePath: string;

  constructor(workspace: string, fixturePath: string) {
    this.fixturePath = resolveFixturePath(workspace, fixturePath);
  }

  async search(request: KnowledgeSearchRequest): Promise<KnowledgeSearchResult> {
    const normalized = normalizeKnowledgeSearchRequest(request);
    const { fixture, sha256 } = await readFixture(this.fixturePath);
    const matchingChunks = fixture.queries
      .filter((entry) => entry.match === normalized.query)
      .flatMap((entry) => entry.chunks)
      .filter((chunk) => {
        if (normalized.knowledgeBases.length === 0) return true;
        const knowledgeBase = chunk.metadata.knowledgeBase;
        return typeof knowledgeBase === "string" && normalized.knowledgeBases.includes(knowledgeBase);
      });
    const chunks = matchingChunks.slice(0, normalized.topK);
    const requestIdentity = JSON.stringify({
      provider: "FIXTURE",
      query: normalized.query,
      topK: normalized.topK,
      knowledgeBases: normalized.knowledgeBases,
    });
    const queryId = `kq_${createHash("sha256")
      .update(requestIdentity)
      .update("\n")
      .update(sha256)
      .digest("hex")
      .slice(0, 32)}`;

    return {
      queryId,
      provider: "FIXTURE",
      query: normalized.query,
      chunks,
      retrieval: { ...fixture.retrieval },
    };
  }
}

export async function createConfiguredKnowledgeProvider(
  workspace: string,
  env: NodeJS.ProcessEnv = process.env,
): Promise<KnowledgeProvider> {
  const mode = env.ENGIKNOW_KNOWLEDGE_MODE?.trim().toLowerCase();
  if (!mode) {
    throw new KnowledgeError(
      "KNOWLEDGE_PROVIDER_NOT_CONFIGURED",
      "No knowledge provider is configured; set ENGIKNOW_KNOWLEDGE_MODE explicitly",
    );
  }
  if (mode !== "fixture") {
    throw new KnowledgeError(
      "KNOWLEDGE_PROVIDER_MODE_UNSUPPORTED",
      `Unsupported knowledge provider mode: ${mode}`,
    );
  }
  const fixturePath = env.ENGIKNOW_KNOWLEDGE_FIXTURE?.trim();
  if (!fixturePath) {
    throw new KnowledgeError(
      "KNOWLEDGE_PROVIDER_NOT_CONFIGURED",
      "Fixture mode requires ENGIKNOW_KNOWLEDGE_FIXTURE",
    );
  }
  return new FixtureKnowledgeProvider(workspace, fixturePath);
}
