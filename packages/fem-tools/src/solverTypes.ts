import type { FemEngineeringBaseTransientAnalysisSpecV2Input } from "./analysisSpecTypes.js";

export type FemSolverKey = "opensees" | "openseespy" | "ansys";

export type FemSolverDisplayName<S extends FemSolverKey = FemSolverKey> =
  S extends "ansys" ? "ANSYS" : "OPENSEESPY";

export type FemSolverExecutionMode<S extends FemSolverKey = FemSolverKey> =
  S extends "ansys" ? "ISOLATED_PROCESS" : "ISOLATED_WORKER_PROCESS";

export interface FemAnsysModelUnits {
  length: "m" | "cm" | "mm";
  time: "s" | "ms";
}

export interface FemAnsysV2Options {
  analysisSpec: FemEngineeringBaseTransientAnalysisSpecV2Input;
  confirmedBundleFingerprint: string;
  renderManifestPath?: string;
}

export interface FemAnsysV2ResultRequest {
  requestId: string;
  quantity: "DISPLACEMENT" | "REACTION_FORCE";
  target: { type: "NODE"; id: number };
  component: "X" | "Y";
}

export type FemAnsysV2Damping =
  | { type: "NONE" }
  | { type: "RAYLEIGH"; alphaM: number; betaK: number };

export interface FemAnsysV2Admission {
  schema: "FEMAGENT_ANSYS_V2_EXECUTION_ADMISSION_V1";
  status: "ADMITTED";
  profile: "ANSYS_APDL_TRANSIENT_UNIFORM_BASE_V2";
  analysisSpecFingerprint: string;
  declaredModelSpecFingerprint: string;
  binding:
    | {
        mode: "EXPLICIT_BUNDLE_CONFIRMATION";
        confirmedBundleFingerprint: string;
        currentBundleFingerprint: string;
        targetIdPolicy: "IDENTITY";
        semanticEquivalence: "NOT_MACHINE_PROVEN";
      }
    | {
        mode: "DETERMINISTIC_MODEL_SPEC_RENDER";
        confirmedBundleFingerprint: string;
        currentBundleFingerprint: string;
        targetIdPolicy: "IDENTITY";
        semanticEquivalence: "MACHINE_PROVEN_RENDER_BINDING";
        renderManifestPath: string;
        renderFingerprint: string;
        renderer: {
          name: "ANSYS_FRAME_2D_BEAM3_V1";
          version: "1.0";
          elementMapping: "BEAM3_PLANAR_EULER_BERNOULLI";
          massMapping: "MASS21_EXPLICIT_MASSX_MASSY";
        };
      };
  modelUnits: FemAnsysModelUnits;
  load: {
    path: string;
    sha256: string;
    format: "FEMAGENT_LOAD_CSV_V1";
    loadKind: "EARTHQUAKE";
    applicationType: "UNIFORM_EXCITATION";
    component: "X" | "Y";
    quantity: "ACCELERATION";
    canonicalUnit: "m/s2";
    modelUnit: string;
    accelerationFactorFromMPerS2: number;
    sampleCount: number;
  };
  time: {
    timeStepModel: number;
    durationModel: number;
    analysisSteps: number;
    timeUnit: "s" | "ms";
  };
  damping: FemAnsysV2Damping;
  resultRequests: FemAnsysV2ResultRequest[];
  executionIntentFingerprint: string;
}

export interface FemSolverOptions {
  modelUnits?: FemAnsysModelUnits;
  ansysV2?: FemAnsysV2Options;
  responsePlanPath?: string;
  analysisManifestPath?: string;
}

export interface FemSolverStatus<S extends FemSolverKey = FemSolverKey> {
  schemaVersion: "1.0";
  kind: "solver_status";
  solver: FemSolverDisplayName<S>;
  available: boolean;
  executionMode: FemSolverExecutionMode<S>;
  capabilities: string[];
  package?: string;
  packageVersion?: string | null;
  engineVersion?: string | null;
  runtime?: string;
  configuredPath?: string | null;
  configuration?: Record<string, unknown>;
  reason?: string | null;
}

export interface FemSolverPreflight<S extends FemSolverKey = FemSolverKey> {
  schemaVersion: "1.0";
  kind: "solver_preflight";
  solver: FemSolverDisplayName<S>;
  status: "READY" | "BLOCKED";
  checks: Array<{ code: string; status: "PASSED" | "FAILED" | "SKIPPED" }>;
  warnings: Array<Record<string, unknown>>;
  model: Record<string, unknown>;
  load: Record<string, unknown>;
  responsePlan?: Record<string, unknown> | null;
  analysisAdmission?: FemAnsysV2Admission;
  executionEstimate: {
    analysisSteps: number | null;
    mode?: string;
  };
}

export interface FemSolverRun<S extends FemSolverKey = FemSolverKey> {
  schemaVersion: "1.0";
  kind: "solver_run";
  runId: string;
  caseFingerprint: string;
  executionInputFingerprint?: string | null;
  status: "COMPLETED";
  solver: {
    name: FemSolverDisplayName<S>;
    executionMode: FemSolverExecutionMode<S>;
    packageVersion?: string | null;
    engineVersion?: string | null;
    runtime?: string;
    configuredPath?: string;
    solverOutcome?: string;
  };
  model: Record<string, unknown>;
  load: Record<string, unknown>;
  responsePlan?: Record<string, unknown> | null;
  analysisAdmission?: FemAnsysV2Admission;
  injection?: Record<string, unknown>;
  analysis: Record<string, unknown>;
  summary: Record<string, unknown>;
  outputs: Record<string, string>;
}
