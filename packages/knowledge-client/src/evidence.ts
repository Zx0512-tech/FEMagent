import { createHash } from "node:crypto";

import type {
  FemEngineeringEvidence,
  FemEngineeringEvidenceReport,
} from "@femagent/fem-tools";

import type { KnowledgeEvidence, KnowledgeSearchResult } from "./types.js";

export interface UnifiedEvidenceLimitation {
  source: "KNOWLEDGE" | "ENGINEERING";
  code: string;
  message: string;
}

export interface UnifiedEvidenceBundle {
  schema: "FEMAGENT_UNIFIED_EVIDENCE_V1";
  projectId: string;
  knowledgeEvidence: KnowledgeEvidence[];
  engineeringEvidence: FemEngineeringEvidence[];
  limitations: UnifiedEvidenceLimitation[];
}

export interface ComposeUnifiedEvidenceInput {
  projectId: string;
  knowledgeEvidence: KnowledgeEvidence[];
  engineeringReport: FemEngineeringEvidenceReport;
}

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

export function composeUnifiedEvidenceBundle(
  input: ComposeUnifiedEvidenceInput,
): UnifiedEvidenceBundle {
  const knowledgeLimitations: UnifiedEvidenceLimitation[] = input.knowledgeEvidence
    .filter((evidence) => evidence.status === "LIMITED")
    .map((evidence) => ({
      source: "KNOWLEDGE",
      code: "KNOWLEDGE_EVIDENCE_LIMITED",
      message: `${evidence.evidenceId}: ${evidence.claim}`,
    }));

  const engineeringLimitations: UnifiedEvidenceLimitation[] = input.engineeringReport.limitations.map(
    (limitation) => ({
      source: "ENGINEERING",
      code: `ENGINEERING_EVIDENCE_${limitation.status}`,
      message: `${limitation.evidenceId}: ${limitation.claim}`,
    }),
  );

  return {
    schema: "FEMAGENT_UNIFIED_EVIDENCE_V1",
    projectId: input.projectId,
    knowledgeEvidence: input.knowledgeEvidence,
    engineeringEvidence: input.engineeringReport.verifiedEvidence,
    limitations: [...knowledgeLimitations, ...engineeringLimitations],
  };
}
