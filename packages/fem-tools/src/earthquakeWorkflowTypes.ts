import type {
  FemEngineeringAnalysisRequirementDraft,
  FemAnalysisRequirementCompletion,
  FemAnalysisRequirementSemanticContext,
} from "./analysisRequirementTypes.js";
import type { FemEngineeringAnalysisSpecV2Input } from "./analysisSpecTypes.js";
import type { FemEngineeringModelSpecInput } from "./modelSpecTypes.js";
import type {
  FemSolverKey,
  FemSolverOptions,
  FemSolverPreflight,
  FemSolverRun,
} from "./solverTypes.js";
import type { FemResultManifest } from "./resultTypes.js";

export type FemEarthquakeWorkflowSolver = "opensees" | "ansys";

export type FemEarthquakeWorkflowPreparationStatus =
  | "NEEDS_INPUT"
  | "ANALYSIS_NOT_READY"
  | "PREFLIGHT_BLOCKED"
  | "READY_FOR_CONFIRMATION";

export interface FemEarthquakeWorkflowRunRequest {
  solver: FemEarthquakeWorkflowSolver;
  modelPath: string;
  solverOptions: FemSolverOptions;
}

export interface FemEarthquakeWorkflowManifestRef {
  path: string;
  sha256: string;
}

export interface FemEarthquakeWorkflowPreparation {
  schema: "FEMAGENT_EARTHQUAKE_WORKFLOW_PREPARATION_V1";
  status: FemEarthquakeWorkflowPreparationStatus;
  solver: FemEarthquakeWorkflowSolver;
  analysisCompletion: FemAnalysisRequirementCompletion;
  analysisReadiness: Record<string, unknown> | null;
  render: Record<string, unknown> | null;
  modelInspection: Record<string, unknown> | null;
  preflight: FemSolverPreflight<FemSolverKey> | null;
  solverRunRequest: FemEarthquakeWorkflowRunRequest | null;
  workflowManifest: FemEarthquakeWorkflowManifestRef | null;
  warnings: Array<Record<string, unknown>>;
}

export interface FemEarthquakeWorkflowPrepareInput {
  solver: FemEarthquakeWorkflowSolver;
  draft: FemEngineeringAnalysisRequirementDraft;
  modelSpec: FemEngineeringModelSpecInput;
  loadArtifactPath: string;
  semanticContext?: FemAnalysisRequirementSemanticContext;
  solverModelPath?: string;
}

export interface FemEarthquakeWorkflowEngineeringSummary {
  requestId: string;
  quantity: string;
  target: Record<string, unknown> | null;
  component: string | null;
  unit: string | null;
  referenceFrame: string | null;
  abscissa: Record<string, unknown> | null;
  sampleCount: number | null;
  min: number | null;
  max: number | null;
  absolutePeak: number | null;
  abscissaAtAbsolutePeak: number | null;
}

export interface FemEarthquakeWorkflowSummary {
  schema: "FEMAGENT_EARTHQUAKE_WORKFLOW_SUMMARY_V1";
  status: "COMPLETED" | "LIMITED";
  workflowId: string;
  workflowFingerprint: string;
  workflowManifest: FemEarthquakeWorkflowManifestRef;
  run: {
    runId: string;
    caseFingerprint: string;
    manifestPath: string;
    solver: FemSolverRun<FemSolverKey>["solver"];
  };
  analysisSpecFingerprint: string;
  modelSpecFingerprint: string;
  resultInspection: FemResultManifest;
  engineeringSummary: FemEarthquakeWorkflowEngineeringSummary[];
  issues: Array<Record<string, unknown>>;
  limitations: Array<Record<string, unknown>>;
}

export interface FemEarthquakeWorkflowManifest {
  schema: "FEMAGENT_EARTHQUAKE_WORKFLOW_V1";
  status: "READY_FOR_CONFIRMATION";
  workflowId: string;
  workflowFingerprint: string;
  solver: FemEarthquakeWorkflowSolver;
  modelSpecFingerprint: string;
  analysisSpecFingerprint: string;
  analysisSpec: FemEngineeringAnalysisSpecV2Input;
  loadArtifact: Record<string, unknown>;
  solverBinding: Record<string, unknown>;
  solverRunRequest: FemEarthquakeWorkflowRunRequest;
  preflight: FemSolverPreflight<FemSolverKey>;
  postprocessPlan: Array<{
    requestId: string;
    query: Record<string, unknown>;
  }>;
  limitations: Array<Record<string, unknown>>;
}
