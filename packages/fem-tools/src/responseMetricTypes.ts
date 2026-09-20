import type { FemSemanticRoleEntity, FemSemanticRoleType } from "./semanticTypes.js";
import type { FemSolverRun } from "./solverTypes.js";

export type FemEngineeringResponseMetricType =
  | "ROLE_ABSOLUTE_PEAK"
  | "ROLE_RELATIVE_DISPLACEMENT_PEAK"
  | "ROLE_GROUP_REACTION_RESULTANT_PEAK";

export type FemEngineeringResponsePeakQuantity =
  | "DISPLACEMENT"
  | "VELOCITY"
  | "ACCELERATION"
  | "RELATIVE_ACCELERATION"
  | "REACTION_FORCE"
  | "REACTION_MOMENT"
  | "GENERALIZED_FORCE"
  | "DAMPER_RESPONSE";

export type FemEngineeringResponsePeakComponent =
  | "X"
  | "Y"
  | "Z"
  | "N"
  | "VY"
  | "VZ"
  | "T"
  | "MY"
  | "MZ"
  | "FORCE"
  | "DEFORMATION"
  | "VELOCITY"
  | "DISSIPATED_ENERGY";

export type FemEngineeringResponseGeneralizedForceLocation =
  | "END_I"
  | "END_J"
  | "SECTION";

export interface FemRoleAbsolutePeakMetricRequest {
  metricId: string;
  type: "ROLE_ABSOLUTE_PEAK";
  roleId: string;
  quantity: FemEngineeringResponsePeakQuantity;
  component: FemEngineeringResponsePeakComponent;
  location?: FemEngineeringResponseGeneralizedForceLocation;
}

export interface FemRoleRelativeDisplacementPeakMetricRequest {
  metricId: string;
  type: "ROLE_RELATIVE_DISPLACEMENT_PEAK";
  targetRoleId: string;
  referenceRoleId: string;
  component: "X" | "Y";
}

export interface FemRoleGroupReactionResultantPeakMetricRequest {
  metricId: string;
  type: "ROLE_GROUP_REACTION_RESULTANT_PEAK";
  roleIds: string[];
  components: ["X", "Y"];
}

export type FemEngineeringResponseMetricRequest =
  | FemRoleAbsolutePeakMetricRequest
  | FemRoleRelativeDisplacementPeakMetricRequest
  | FemRoleGroupReactionResultantPeakMetricRequest;

export interface FemEngineeringResponseMetricsRequest {
  schema: "FEMAGENT_ENGINEERING_RESPONSE_METRIC_REQUEST_V1";
  runRef: string;
  modelPath: string;
  semanticManifestPath: string;
  metrics: FemEngineeringResponseMetricRequest[];
}

export interface FemEngineeringResponseMetricRole {
  roleId: string;
  roleType: FemSemanticRoleType;
  entity: FemSemanticRoleEntity;
  entityValidation: "STATICALLY_CONFIRMED" | "NOT_STATICALLY_ENUMERABLE";
  manifestSha256: string;
  modelBundleFingerprint: string;
}

export interface FemEngineeringResponseMetricBase {
  metricId: string;
  type: FemEngineeringResponseMetricType;
  status: "COMPUTED";
  unit: string | null;
  referenceFrame: string | null;
  abscissa: Record<string, unknown> | null;
  sampleCount: number;
  absolutePeak: number;
  abscissaAtAbsolutePeak: number;
}

export interface FemRoleAbsolutePeakMetric
  extends FemEngineeringResponseMetricBase {
  type: "ROLE_ABSOLUTE_PEAK";
  role: FemEngineeringResponseMetricRole;
  quantity: string;
  target: FemSemanticRoleEntity;
  component: string;
  location?: string;
  min: number;
  max: number;
  source: Record<string, unknown> | null;
}

export interface FemRoleRelativeDisplacementPeakMetric
  extends FemEngineeringResponseMetricBase {
  type: "ROLE_RELATIVE_DISPLACEMENT_PEAK";
  targetRole: FemEngineeringResponseMetricRole;
  referenceRole: FemEngineeringResponseMetricRole;
  quantity: "RELATIVE_DISPLACEMENT";
  component: "X" | "Y";
  formula: "target - reference";
  min: number;
  max: number;
  valueAtAbsolutePeak: number;
  sources: Array<Record<string, unknown> | null>;
}

export interface FemRoleGroupReactionResultantPeakMetric
  extends FemEngineeringResponseMetricBase {
  type: "ROLE_GROUP_REACTION_RESULTANT_PEAK";
  roles: FemEngineeringResponseMetricRole[];
  quantity: "REACTION_FORCE_RESULTANT";
  components: ["X", "Y"];
  formula: "sqrt((sum Rx)^2 + (sum Ry)^2)";
  aggregation: "SIGNED_COMPONENT_SUM_THEN_VECTOR_MAGNITUDE";
  minResultant: number;
  maxResultant: number;
  componentSumsAtAbsolutePeak: { X: number; Y: number };
  sources: Array<{
    roleId: string;
    X: Record<string, unknown> | null;
    Y: Record<string, unknown> | null;
  }>;
}

export type FemEngineeringResponseMetric =
  | FemRoleAbsolutePeakMetric
  | FemRoleRelativeDisplacementPeakMetric
  | FemRoleGroupReactionResultantPeakMetric;

export interface FemEngineeringResponseMetricIssue {
  metricId: string;
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export interface FemEngineeringResponseMetricsReport {
  schema: "FEMAGENT_ENGINEERING_RESPONSE_METRICS_V1";
  status: "COMPLETED" | "LIMITED";
  requestFingerprint: string;
  run: {
    runId: string;
    caseFingerprint: string;
    solver: FemSolverRun["solver"];
    modelBundleFingerprint: string;
  };
  semantic: {
    modelPath: string;
    modelBundleFingerprint: string;
    manifestPath: string;
    manifestSha256: string;
  };
  metrics: FemEngineeringResponseMetric[];
  issues: FemEngineeringResponseMetricIssue[];
  limitations: Array<{ code: string; message: string }>;
}
