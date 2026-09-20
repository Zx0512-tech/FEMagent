import type {
  FemEngineeringResponseMetricsReport,
  FemEngineeringResponseMetricsRequest,
} from "./responseMetricTypes.js";
import type { FemSolverRun } from "./solverTypes.js";

export interface FemEngineeringPerformanceConstraint {
  constraintId: string;
  metricId: string;
  operator: "MAXIMUM";
  limit: number;
  unit: string;
  label?: string;
}

export interface FemEngineeringPerformanceRequest {
  schema: "FEMAGENT_ENGINEERING_PERFORMANCE_REQUEST_V1";
  metricsRequest: FemEngineeringResponseMetricsRequest;
  constraints: FemEngineeringPerformanceConstraint[];
}

export type FemEngineeringConstraintStatus =
  | "SATISFIED"
  | "VIOLATED"
  | "NOT_EVALUABLE";

export interface FemEngineeringConstraintEvaluation {
  constraintId: string;
  metricId: string;
  operator: "MAXIMUM";
  status: FemEngineeringConstraintStatus;
  observed: number | null;
  limit: number;
  unit: string;
  utilization: number | null;
  reserve: number | null;
  label?: string;
  metric?: Record<string, unknown>;
  issue: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  } | null;
}

export interface FemEngineeringPerformanceEvaluation {
  schema: "FEMAGENT_ENGINEERING_PERFORMANCE_EVALUATION_V1";
  status: "FEASIBLE" | "INFEASIBLE" | "LIMITED";
  metricsRequestFingerprint: string;
  constraintSetFingerprint: string;
  evaluationFingerprint: string;
  run: {
    runId: string;
    caseFingerprint: string;
    solver: FemSolverRun["solver"];
    modelBundleFingerprint: string;
  };
  semantic: FemEngineeringResponseMetricsReport["semantic"];
  metricsStatus: FemEngineeringResponseMetricsReport["status"];
  constraints: FemEngineeringConstraintEvaluation[];
  summary: {
    constraintCount: number;
    satisfied: number;
    violated: number;
    notEvaluable: number;
  };
  governingConstraint: {
    constraintId: string;
    metricId: string;
    status: "SATISFIED" | "VIOLATED";
    basis: "MAXIMUM_UTILIZATION" | "MINIMUM_RESERVE";
    utilization: number | null;
    reserve: number;
  } | null;
  metricsReport: FemEngineeringResponseMetricsReport;
  limitations: Array<{ code: string; message: string }>;
}
