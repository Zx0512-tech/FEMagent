export interface FemSolverPreflight {
  schemaVersion: "1.0";
  kind: "solver_preflight";
  solver: "OPENSEESPY";
  status: "READY" | "BLOCKED";
  checks: Array<{ code: string; status: "PASSED" | "FAILED" }>;
  warnings: Array<Record<string, unknown>>;
  model: Record<string, unknown>;
  load: Record<string, unknown>;
  executionEstimate: {
    analysisSteps: number | null;
    mode?: string;
  };
}

export interface FemSolverRun {
  schemaVersion: "1.0";
  kind: "solver_run";
  runId: string;
  caseFingerprint: string;
  status: "COMPLETED";
  solver: {
    name: "OPENSEESPY";
    packageVersion: string | null;
    engineVersion: string | null;
    executionMode: "ISOLATED_WORKER_PROCESS";
  };
  model: Record<string, unknown>;
  load: Record<string, unknown>;
  analysis: Record<string, unknown>;
  summary: Record<string, unknown>;
  outputs: Record<string, string>;
}
