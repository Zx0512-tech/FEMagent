import { createHash } from "node:crypto";

import type { KnowledgeEvidence, KnowledgeSearchResult } from "./types.js";

export function knowledgeEvidenceFromSearchResult(
  result: KnowledgeSearchResult,
): KnowledgeEvidence[] {
  return result.chunks.map((chunk) => ({
    evidenceId: `ke_${createHash("sha256")
      .update(result.queryId)
      .update("\n")
      .update(chunk.chunkId)
      .digest("hex")
      .slice(0, 32)}`,
    status: "RETRIEVED",
    claim: chunk.content,
    chunk: {
      chunkId: chunk.chunkId,
      documentId: chunk.documentId,
      title: chunk.title,
      section: chunk.section,
      page: chunk.page,
      source: chunk.source,
    },
    retrieval: {
      queryId: result.queryId,
      provider: result.provider,
      retrievalScore: chunk.retrievalScore,
      rerankScore: chunk.rerankScore,
      strategy: result.retrieval.strategy,
    },
  }));
}
