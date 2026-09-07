import type { FemEngineeringModelSpecInput, FemModelSpecValidation } from "./modelSpecTypes.js";

export type FemAnalysisSpecForceUnit = "N" | "kN";
export type FemAnalysisSpecStatus = "VALID" | "INVALID";
export type FemAnalysisSpecIssueSeverity = "ERROR" | "WARNING";
export type FemAnalysisType = "LINEAR_STATIC";

export interface FemAnalysisSpecUnits {
  force: FemAnalysisSpecForceUnit;
}

export interface FemAnalysisNodalLoad {
  nodeId: number;
  FX: number;
  FY: number;
  MZ: number;
}

export interface FemAnalysisLoadCase {
  loadCaseId: string;
  nodalLoads: FemAnalysisNodalLoad[];
}

export interface FemAnalysisResultTarget {
  type: "NODE" | "ELEMENT";
  id: number;
}

interface FemAnalysisResultRequestBase {
  requestId: string;
  loadCaseId: string;
  target: FemAnalysisResultTarget;
}

export interface FemAnalysisNodeDisplacementRequest extends FemAnalysisResultRequestBase {
  quantity: "DISPLACEMENT";
  target: { type: "NODE"; id: number };
  component: "X" | "Y";
}

export interface FemAnalysisNodeReactionForceRequest extends FemAnalysisResultRequestBase {
  quantity: "REACTION_FORCE";
  target: { type: "NODE"; id: number };
  component: "X" | "Y";
}

export interface FemAnalysisNodeReactionMomentRequest extends FemAnalysisResultRequestBase {
  quantity: "REACTION_MOMENT";
  target: { type: "NODE"; id: number };
  component: "Z";
}

export interface FemAnalysisElementGeneralizedForceRequest extends FemAnalysisResultRequestBase {
  quantity: "GENERALIZED_FORCE";
  target: { type: "ELEMENT"; id: number };
  component: "N" | "VY" | "MZ";
  location: "END_I" | "END_J";
}

export type FemAnalysisResultRequest =
  | FemAnalysisNodeDisplacementRequest
  | FemAnalysisNodeReactionForceRequest
  | FemAnalysisNodeReactionMomentRequest
  | FemAnalysisElementGeneralizedForceRequest;

export interface FemEngineeringAnalysisSpecInput {
  schemaVersion: "1.0";
  kind: "engineering_analysis_spec";
  modelSpecFingerprint: string;
  analysisType: FemAnalysisType;
  units: FemAnalysisSpecUnits;
  loadCases: FemAnalysisLoadCase[];
  resultRequests: FemAnalysisResultRequest[];
}

export interface FemAnalysisSpecIssue {
  severity: FemAnalysisSpecIssueSeverity;
  code: string;
  path: string;
  message: string;
}

export interface FemAnalysisSpecValidation {
  schema: "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1";
  status: FemAnalysisSpecStatus;
  issues: FemAnalysisSpecIssue[];
  normalizedSpec: FemEngineeringAnalysisSpecInput | null;
  analysisSpecFingerprint: string | null;
}

export type FemAnalysisReadinessStatus = "INVALID_SPEC" | "NOT_READY" | "READY";
export type FemAnalysisReadinessCheckStatus = "PASS" | "FAIL" | "SKIPPED";
export type FemAnalysisResponseUnit = string;

interface FemAnalysisResponseMappingBase {
  requestId: string;
  quantity: FemAnalysisResultRequest["quantity"];
  target: FemAnalysisResultTarget;
  component: string;
  unit: FemAnalysisResponseUnit;
}

export interface FemAnalysisNodeDispMapping extends FemAnalysisResponseMappingBase {
  access: "NODE_DISP";
  target: { type: "NODE"; id: number };
  quantity: "DISPLACEMENT";
  component: "X" | "Y";
  dof: 1 | 2;
  referenceFrame: "GLOBAL";
}

export interface FemAnalysisNodeReactionMapping extends FemAnalysisResponseMappingBase {
  access: "NODE_REACTION";
  target: { type: "NODE"; id: number };
  quantity: "REACTION_FORCE" | "REACTION_MOMENT";
  component: "X" | "Y" | "Z";
  dof: 1 | 2 | 3;
  referenceFrame: "GLOBAL";
}

export interface FemAnalysisElementLocalForceMapping extends FemAnalysisResponseMappingBase {
  access: "ELEMENT_LOCAL_FORCE";
  target: { type: "ELEMENT"; id: number };
  quantity: "GENERALIZED_FORCE";
  component: "N" | "VY" | "MZ";
  location: "END_I" | "END_J";
  response: "localForce";
  index: 0 | 1 | 2 | 3 | 4 | 5;
  vectorLength: 6;
  referenceFrame: "ELEMENT_LOCAL";
}

export type FemAnalysisResponseMapping =
  | FemAnalysisNodeDispMapping
  | FemAnalysisNodeReactionMapping
  | FemAnalysisElementLocalForceMapping;

export interface FemAnalysisReadiness {
  schema: "FEMAGENT_ANALYSIS_READINESS_V1";
  status: FemAnalysisReadinessStatus;
  profile: "OPENSEES_FRAME_2D_LINEAR_STATIC_V1";
  modelSpecFingerprint: string | null;
  analysisSpecFingerprint: string | null;
  validation: {
    modelSpec: Pick<FemModelSpecValidation, "schema" | "status" | "issues">;
    analysisSpec: Pick<FemAnalysisSpecValidation, "schema" | "status" | "issues">;
  };
  checks: {
    modelReadiness: { status: FemAnalysisReadinessCheckStatus; report?: Record<string, unknown> };
    modelBinding: { status: FemAnalysisReadinessCheckStatus; expected?: string; received?: string };
    unitCompatibility: {
      status: FemAnalysisReadinessCheckStatus;
      modelForce?: FemAnalysisSpecForceUnit;
      analysisForce?: FemAnalysisSpecForceUnit;
    };
    loadTargets: { status: FemAnalysisReadinessCheckStatus; missingNodeIds?: number[] };
    resultTargets: {
      status: FemAnalysisReadinessCheckStatus;
      missingNodeIds?: number[];
      missingElementIds?: number[];
    };
    reactionSemantics: {
      status: FemAnalysisReadinessCheckStatus;
      unrestrainedRequests?: string[];
    };
    responseMapping: {
      status: FemAnalysisReadinessCheckStatus;
      channels: FemAnalysisResponseMapping[];
    };
  };
  issues: FemAnalysisSpecIssue[];
}

export interface FemOpenSeesAnalysisRenderArtifacts {
  analysisPath: string;
  analysisSha256: string;
  responsePlanPath: string;
  responsePlanSha256: string;
  readinessPath: string;
  readinessSha256: string;
  manifestPath: string;
}

export interface FemOpenSeesAnalysisRenderedResult {
  schema: "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V1";
  status: "RENDERED";
  analysisRenderId: string;
  renderer: {
    name: "OPENSEES_FRAME_2D_LINEAR_STATIC_V1";
    version: "1.0";
  };
  input: {
    modelSpecFingerprint: string;
    analysisSpecFingerprint: string;
    readinessProfile: "OPENSEES_FRAME_2D_LINEAR_STATIC_V1";
    units: FemEngineeringModelSpecInput["units"];
    normalizedModelSpec: FemEngineeringModelSpecInput;
    normalizedAnalysisSpec: FemEngineeringAnalysisSpecInput;
  };
  loadCaseId: string;
  responseMappings: FemAnalysisResponseMapping[];
  artifacts: FemOpenSeesAnalysisRenderArtifacts;
  analysisRenderFingerprint: string;
}

export interface FemOpenSeesAnalysisBlockedResult {
  schema: "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V1";
  status: "BLOCKED";
  reason: "ANALYSIS_NOT_READY";
  readiness: FemAnalysisReadiness;
  analysisRenderId: null;
  artifacts: null;
  analysisRenderFingerprint: null;
}

export type FemOpenSeesAnalysisRenderResult =
  | FemOpenSeesAnalysisRenderedResult
  | FemOpenSeesAnalysisBlockedResult;
