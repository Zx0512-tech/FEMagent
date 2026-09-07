export type KnowledgeProviderName = "FIXTURE" | "RAGFLOW";
export type KnowledgeEvidenceStatus = "RETRIEVED" | "LIMITED";

export interface KnowledgeSearchRequest {
  query: string;
  topK?: number;
  knowledgeBases?: string[];
}

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

export interface KnowledgeSearchResult {
  queryId: string;
  provider: KnowledgeProviderName;
  query: string;
  chunks: KnowledgeChunk[];
  retrieval: {
    strategy: string;
    embeddingModel: string | null;
    rerankerModel: string | null;
  };
}

export interface KnowledgeEvidence {
  evidenceId: string;
  status: KnowledgeEvidenceStatus;
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
    provider: KnowledgeProviderName;
    retrievalScore: number | null;
    rerankScore: number | null;
    strategy: string;
  };
}
