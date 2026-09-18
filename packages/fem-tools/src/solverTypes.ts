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
  injection?: Record<string, unknown>;
  analysis: Record<string, unknown>;
  summary: Record<string, unknown>;
  outputs: Record<string, string>;
}
