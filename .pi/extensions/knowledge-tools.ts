import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  createConfiguredKnowledgeProvider,
  knowledgeEvidenceFromSearchResult,
} from "@femagent/knowledge-client";
import { Type } from "typebox";

export default function knowledgeToolsExtension(pi: ExtensionAPI) {
  pi.registerTool({
    name: "engiknow_search",
    label: "Search EngiKnow Knowledge",
    description: "Search the explicitly configured engineering knowledge provider and return normalized citation evidence. SAFE and read-only; PR20 fixture mode is an integration harness, not live RAGFlow retrieval.",
    promptSnippet: "Search configured engineering knowledge for methodology or citation evidence while keeping FEM numerical truth in FEM tools and solver artifacts",
    promptGuidelines: [
      "Retrieved knowledge is guidance and citation evidence; it is not solver truth and must not override model, load, result, unit, target, provenance, or artifact facts from FEM tools.",
      "When provider is FIXTURE, describe it only as fixture-backed integration evidence; never claim that RAGFlow, an embedding model, or a reranker performed the retrieval.",
      "Preserve returned title, section, page, source, and retrieval scores exactly; never invent missing citation metadata.",
      "Use FEM Model/Load/Solver/Result/Evidence tools for numerical engineering truth.",
      "If the provider is not configured or fixture validation fails, surface the provider error instead of pretending retrieval succeeded.",
    ],
    parameters: Type.Object({
      query: Type.String({ description: "Engineering knowledge query; must be non-empty after trimming" }),
      topK: Type.Optional(Type.Integer({ minimum: 1, maximum: 20, description: "Maximum returned chunks; defaults to 8" })),
      knowledgeBases: Type.Optional(Type.Array(Type.String({ minLength: 1 }), { description: "Optional logical knowledge-base IDs" })),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const provider = await createConfiguredKnowledgeProvider(ctx.cwd, process.env);
      const result = await provider.search({
        query: params.query,
        ...(params.topK === undefined ? {} : { topK: params.topK }),
        ...(params.knowledgeBases === undefined ? {} : { knowledgeBases: params.knowledgeBases }),
      });
      const evidence = knowledgeEvidenceFromSearchResult(result);
      const details = { result, evidence };
      return { content: [{ type: "text", text: JSON.stringify(details, null, 2) }], details };
    },
  });
}
