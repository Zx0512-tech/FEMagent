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
