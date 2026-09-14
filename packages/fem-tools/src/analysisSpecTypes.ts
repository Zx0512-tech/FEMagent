export * from "./analysisSpecTypesLegacy.js";

import type {
  FemAnalysisElementLocalForceMapping,
  FemAnalysisNodeDispMapping,
  FemAnalysisNodeReactionMapping,
  FemAnalysisReadiness as FemAnalysisReadinessV1,
  FemAnalysisReadinessCheckStatus,
  FemAnalysisResponseMapping as FemAnalysisResponseMappingV1,
  FemAnalysisSpecIssue,
  FemEngineeringAnalysisSpecV2Input,
  FemEngineeringModelSpecInput,
  FemModelSpecValidation,
  FemOpenSeesAnalysisBlockedResult as FemOpenSeesAnalysisBlockedResultV1,
  FemOpenSeesAnalysisRenderArtifacts,
  FemOpenSeesAnalysisRenderedResult as FemOpenSeesAnalysisRenderedResultV1,
} from "./analysisSpecTypesLegacy.js";

export type FemAnalysisReadinessProfileV2 =
  | "OPENSEES_FRAME_2D_LINEAR_STATIC_V2"
  | "OPENSEES_FRAME_2D_MODAL_V2"
  | "OPENSEES_FRAME_2D_TRANSIENT_NODAL_FORCE_V2"
  | "OPENSEES_FRAME_2D_TRANSIENT_UNIFORM_BASE_V2";

export interface FemAnalysisNodeVelocityMapping {
  requestId: string;
  quantity: "VELOCITY";
  target: { type: "NODE"; id: number };
  component: "X" | "Y";
  access: "NODE_VEL";
  dof: 1 | 2;
  unit: string;
  referenceFrame: "GLOBAL" | "RELATIVE";
}

export interface FemAnalysisNodeAccelerationMapping {
  requestId: string;
  quantity: "ACCELERATION" | "RELATIVE_ACCELERATION";
  target: { type: "NODE"; id: number };
  component: "X" | "Y";
  access: "NODE_ACCEL";
  dof: 1 | 2;
  unit: string;
  referenceFrame: "GLOBAL" | "RELATIVE";
}

export interface FemAnalysisModalEigenvalueMapping {
  requestId: string;
  quantity: "EIGENVALUE" | "NATURAL_FREQUENCY" | "PERIOD";
  mode: number;
  access: "MODAL_EIGENVALUE";
  unit: string;
}

export interface FemAnalysisModalModeShapeMapping {
  requestId: string;
  quantity: "MODE_SHAPE";
  mode: number;
  target: { type: "NODE"; id: number };
  component: "X" | "Y" | "RZ";
  access: "NODE_EIGENVECTOR";
  dof: 1 | 2 | 3;
  unit: "1";
  normalization: "OPENSEES_NATIVE";
}

export type FemAnalysisResponseMappingV2 =
  | FemAnalysisResponseMappingV1
  | FemAnalysisNodeVelocityMapping
  | FemAnalysisNodeAccelerationMapping
  | FemAnalysisModalEigenvalueMapping
  | FemAnalysisModalModeShapeMapping;

export type FemAnalysisResponseMapping = FemAnalysisResponseMappingV2;

interface FemAnalysisV2Check {
  status: FemAnalysisReadinessCheckStatus;
  [key: string]: unknown;
}

export interface FemAnalysisReadinessV2 {
  schema: "FEMAGENT_ANALYSIS_READINESS_V2";
  status: "INVALID_SPEC" | "NOT_READY" | "READY";
  profile: FemAnalysisReadinessProfileV2;
  modelSpecFingerprint: string | null;
  analysisSpecFingerprint: string | null;
  validation: {
    modelSpec: Pick<FemModelSpecValidation, "schema" | "status" | "issues">;
    analysisSpec: {
      schema: "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1";
      status: "VALID" | "INVALID";
      issues: FemAnalysisSpecIssue[];
    };
  };
  checks: {
    modelReadiness: FemAnalysisV2Check;
    modelBinding: FemAnalysisV2Check;
    resultTargets: FemAnalysisV2Check;
    responseMapping: FemAnalysisV2Check & { channels: FemAnalysisResponseMappingV2[] };
    unitCompatibility?: FemAnalysisV2Check;
    loadTargets?: FemAnalysisV2Check;
    reactionSemantics?: FemAnalysisV2Check;
    modalMass?: FemAnalysisV2Check;
    modeCount?: FemAnalysisV2Check;
    loadArtifact?: FemAnalysisV2Check;
    excitationSemantics?: FemAnalysisV2Check;
    timeCompatibility?: FemAnalysisV2Check;
    unitConversions?: FemAnalysisV2Check;
  };
  issues: FemAnalysisSpecIssue[];
}

export type FemAnalysisReadiness = FemAnalysisReadinessV1 | FemAnalysisReadinessV2;

export interface FemOpenSeesAnalysisRenderedResultV2 {
  schema: "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V2";
  status: "RENDERED";
  analysisRenderId: string;
  renderer: {
    name: FemAnalysisReadinessProfileV2;
    version: "2.0";
  };
  input: {
    modelSpecFingerprint: string;
    analysisSpecFingerprint: string;
    readinessProfile: FemAnalysisReadinessProfileV2;
    units: FemEngineeringModelSpecInput["units"];
    normalizedModelSpec: FemEngineeringModelSpecInput;
    normalizedAnalysisSpec: FemEngineeringAnalysisSpecV2Input;
  };
  responseMappings: FemAnalysisResponseMappingV2[];
  externalArtifacts: Array<{ path: string; sha256: string; format: string }>;
  unitConversions: Array<{
    quantity: string;
    sourceUnit: string;
    targetUnit: string;
    factor: number;
  }>;
  artifacts: FemOpenSeesAnalysisRenderArtifacts;
  analysisRenderFingerprint: string;
}

export interface FemOpenSeesAnalysisBlockedResultV2 {
  schema: "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V2";
  status: "BLOCKED";
  reason: "ANALYSIS_NOT_READY";
  readiness: FemAnalysisReadinessV2;
  analysisRenderId: null;
  artifacts: null;
  analysisRenderFingerprint: null;
}

export type FemOpenSeesAnalysisRenderedResult =
  | FemOpenSeesAnalysisRenderedResultV1
  | FemOpenSeesAnalysisRenderedResultV2;

export type FemOpenSeesAnalysisBlockedResult =
  | FemOpenSeesAnalysisBlockedResultV1
  | FemOpenSeesAnalysisBlockedResultV2;

export type FemOpenSeesAnalysisRenderResult =
  | FemOpenSeesAnalysisRenderedResult
  | FemOpenSeesAnalysisBlockedResult;

export type {
  FemAnalysisElementLocalForceMapping,
  FemAnalysisNodeDispMapping,
  FemAnalysisNodeReactionMapping,
};
