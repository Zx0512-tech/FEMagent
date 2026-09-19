import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runFemEarthquakeWorkflowPrepare,
  runFemEarthquakeWorkflowSummarize,
  type FemEarthquakeWorkflowPrepareInput,
} from "@femagent/fem-tools";
import { Type } from "typebox";

const semanticContext = Type.Object(
  {
    modelPath: Type.String({ minLength: 1 }),
    manifestPath: Type.String({ minLength: 1 }),
  },
  { additionalProperties: false },
);

function toolResult(report: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(report, null, 2) }],
    details: report,
  };
}

export default function earthquakeWorkflowToolsExtension(pi: ExtensionAPI) {
  pi.registerTool({
    name: "fem_earthquake_workflow_prepare",
    label: "Prepare Earthquake FEM Workflow",
    description:
      "Compose controlled analysis completion, solver-specific earthquake preparation, deterministic rendering/binding, and solver preflight. SAFE: it never starts the requested real analysis.",
    promptSnippet:
      "Prepare a complete earthquake-analysis execution request and preflight it before asking for real solver execution",
    promptGuidelines: [
      "Use this after a canonical earthquake load artifact exists and the user request has been extracted into the PR30 evidence-backed analysis requirement draft.",
      "For OpenSees, PR31 performs Analysis Readiness, verifies positive excited-direction nodal mass, renders the generated analysis, and preflights the exact generated bundle.",
      "For ANSYS, provide solverModelPath for the workspace-local APDL entrypoint. PR31 inspects the exact bundle and binds PR29 admission to its current fingerprint; it does not prove APDL↔ModelSpec semantic equivalence.",
      "If status is NEEDS_INPUT, ANALYSIS_NOT_READY, or PREFLIGHT_BLOCKED, do not call fem_solver_run. Surface the returned missing/conflict/readiness/preflight evidence.",
      "If status is READY_FOR_CONFIRMATION, call fem_solver_run with solver, modelPath, and solverOptions copied verbatim from solverRunRequest. Do not mutate any path, fingerprint, AnalysisSpec, or option between preflight and run.",
      "Real execution must remain on fem_solver_run so the existing permission gate can obtain explicit user approval. This workflow tool must never execute the solver itself.",
      "After fem_solver_run returns COMPLETED, call fem_earthquake_workflow_summarize with the returned runId and the exact workflow manifest path/SHA from preparation.",
    ],
    parameters: Type.Object(
      {
        solver: Type.Union([Type.Literal("opensees"), Type.Literal("ansys")]),
        draft: Type.Record(Type.String(), Type.Unknown(), {
          description: "PR30 FEMAGENT_ANALYSIS_REQUIREMENT_DRAFT_V1 object",
        }),
        modelSpec: Type.Record(Type.String(), Type.Unknown(), {
          description: "Validated/candidate EngineeringModelSpec object",
        }),
        loadArtifactPath: Type.String({
          minLength: 1,
          description: "Workspace-relative canonical FEMAGENT_LOAD_CSV_V1 earthquake artifact",
        }),
        semanticContext: Type.Optional(semanticContext),
        solverModelPath: Type.Optional(
          Type.String({
            minLength: 1,
            description: "Required for ANSYS: workspace-relative APDL model entrypoint",
          }),
        ),
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemEarthquakeWorkflowPrepare(
        ctx.cwd,
        params as unknown as FemEarthquakeWorkflowPrepareInput,
        signal,
      );
      return toolResult(report);
    },
  });

  pi.registerTool({
    name: "fem_earthquake_workflow_summarize",
    label: "Summarize Earthquake FEM Workflow",
    description:
      "Bind a completed solver run back to the exact prepared earthquake workflow, verify result integrity, and return deterministic SUMMARY metrics for every planned response. SAFE and read-only.",
    promptSnippet:
      "Summarize a completed earthquake workflow only after exact workflow/run identity checks",
    promptGuidelines: [
      "Use only the workflowManifest.path and workflowManifest.sha256 returned by READY_FOR_CONFIRMATION preparation; never invent either value.",
      "Pass the runId returned by the permission-gated fem_solver_run call.",
      "The tool verifies solver, AnalysisSpec, ModelSpec/render/bundle identity before querying Result Intelligence.",
      "Do not call this tool to compensate for a failed solver run or a mismatched run. Preserve identity/integrity errors.",
      "Report returned units exactly. In particular, unknown ANSYS units remain unknown and must not be relabeled as SI.",
      "engineeringSummary reports deterministic extrema/absolute peaks only; it is not an engineering PASS/FAIL judgment.",
      "This tool never reruns a solver.",
    ],
    parameters: Type.Object(
      {
        workflowManifestPath: Type.String({ minLength: 1 }),
        workflowManifestSha256: Type.String({
          pattern: "^[0-9a-f]{64}$",
        }),
        runRef: Type.String({ minLength: 1 }),
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemEarthquakeWorkflowSummarize(
        ctx.cwd,
        params.workflowManifestPath,
        params.workflowManifestSha256,
        params.runRef,
        signal,
      );
      return toolResult(report);
    },
  });
}
