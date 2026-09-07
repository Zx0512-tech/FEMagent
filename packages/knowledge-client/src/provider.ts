import type { KnowledgeSearchRequest, KnowledgeSearchResult } from "./types.js";

export const KNOWLEDGE_ERROR_CODES = [
  "KNOWLEDGE_PROVIDER_NOT_CONFIGURED",
  "KNOWLEDGE_PROVIDER_MODE_UNSUPPORTED",
  "KNOWLEDGE_FIXTURE_PATH_OUTSIDE_WORKSPACE",
  "KNOWLEDGE_FIXTURE_NOT_FOUND",
  "INVALID_KNOWLEDGE_FIXTURE",
  "INVALID_KNOWLEDGE_QUERY",
] as const;

export type KnowledgeErrorCode = (typeof KNOWLEDGE_ERROR_CODES)[number];

export class KnowledgeError extends Error {
  readonly code: KnowledgeErrorCode;

  constructor(code: KnowledgeErrorCode, message: string) {
    super(message);
    this.name = "KnowledgeError";
    this.code = code;
  }
}

export interface KnowledgeProvider {
  search(request: KnowledgeSearchRequest): Promise<KnowledgeSearchResult>;
}

export interface NormalizedKnowledgeSearchRequest {
  query: string;
  topK: number;
  knowledgeBases: string[];
}

export function normalizeKnowledgeSearchRequest(
  request: KnowledgeSearchRequest,
): NormalizedKnowledgeSearchRequest {
  const query = typeof request.query === "string" ? request.query.trim().toLowerCase() : "";
  if (!query) {
    throw new KnowledgeError("INVALID_KNOWLEDGE_QUERY", "Knowledge query must be non-empty after trimming");
  }

  const topK = request.topK ?? 8;
  if (!Number.isInteger(topK) || topK < 1 || topK > 20) {
    throw new KnowledgeError("INVALID_KNOWLEDGE_QUERY", "Knowledge topK must be an integer from 1 through 20");
  }

  const knowledgeBases = request.knowledgeBases ?? [];
  if (!Array.isArray(knowledgeBases) || knowledgeBases.some((value) => typeof value !== "string" || !value.trim())) {
    throw new KnowledgeError("INVALID_KNOWLEDGE_QUERY", "knowledgeBases must contain only non-empty strings");
  }

  return {
    query,
    topK,
    knowledgeBases: knowledgeBases.map((value) => value.trim()).sort(),
  };
}
