export type FemModelSpecDimension = "2D";
export type FemModelSpecFamily = "FRAME";
export type FemModelSpecCoordinateSystem = "CARTESIAN_XY";
export type FemModelSpecLengthUnit = "m" | "cm" | "mm";
export type FemModelSpecForceUnit = "N" | "kN";
export type FemModelSpecTimeUnit = "s" | "ms";
export type FemModelSpecDof = "UX" | "UY" | "RZ";
export type FemModelSpecStatus = "VALID" | "INVALID";
export type FemModelSpecIssueSeverity = "ERROR" | "WARNING";
export type FemModelSpecReadinessStatus = "READY" | "NOT_READY" | "INVALID_SPEC";
export type FemModelSpecReadinessCheckStatus = "PASS" | "WARN" | "FAIL" | "SKIPPED";

export interface FemModelSpecUnits {
  length: FemModelSpecLengthUnit;
  force: FemModelSpecForceUnit;
  time: FemModelSpecTimeUnit;
}

export interface FemModelSpecNode {
  id: number;
  x: number;
  y: number;
}

export interface FemModelSpecMaterial {
  id: number;
  type: "LINEAR_ELASTIC";
  youngsModulus: number;
}

export interface FemModelSpecSection {
  id: number;
  type: "FRAME_2D";
  area: number;
  iz: number;
}

export interface FemModelSpecElement {
  id: number;
  type: "ELASTIC_FRAME_2D";
  formulation: "EULER_BERNOULLI";
  nodeI: number;
  nodeJ: number;
  materialId: number;
  sectionId: number;
}

export interface FemModelSpecConstraint {
  nodeId: number;
  dofs: FemModelSpecDof[];
}

export interface FemModelSpecNodalMass {
  nodeId: number;
  mUX: number;
  mUY: number;
}

export interface FemEngineeringModelSpecInput {
  schemaVersion: "1.0";
  kind: "engineering_model_spec";
  dimension: FemModelSpecDimension;
  family: FemModelSpecFamily;
  coordinateSystem: FemModelSpecCoordinateSystem;
  units: FemModelSpecUnits;
  nodes: FemModelSpecNode[];
  materials: FemModelSpecMaterial[];
  sections: FemModelSpecSection[];
  elements: FemModelSpecElement[];
  constraints: FemModelSpecConstraint[];
  nodalMasses: FemModelSpecNodalMass[];
}

export interface FemModelSpecIssue {
  severity: FemModelSpecIssueSeverity;
  code: string;
  path: string;
  message: string;
}

export interface FemModelSpecValidation {
  schema: "FEMAGENT_MODEL_SPEC_VALIDATION_V1";
  status: FemModelSpecStatus;
  issues: FemModelSpecIssue[];
  normalizedSpec: FemEngineeringModelSpecInput | null;
  modelSpecFingerprint: string | null;
}

export interface FemModelSpecReadinessComponent {
  index: number;
  nodeIds: number[];
  elementIds: number[];
}

export interface FemModelSpecReadinessRigidBodyComponent extends FemModelSpecReadinessComponent {
  constraintRank: number;
  deficiency: number;
}

export interface FemModelSpecParallelConnectivityGroup {
  nodeIds: [number, number];
  elementIds: number[];
}

export interface FemModelSpecReadiness {
  schema: "FEMAGENT_MODEL_SPEC_READINESS_V1";
  status: FemModelSpecReadinessStatus;
  profile: "FRAME_2D_ELASTIC_READINESS_V1";
  modelSpecFingerprint: string | null;
  validation: Pick<FemModelSpecValidation, "schema" | "status" | "issues">;
  checks: {
    connectivity: {
      status: FemModelSpecReadinessCheckStatus;
      componentCount: number;
      components: FemModelSpecReadinessComponent[];
    };
    rigidBodyRestraint: {
      status: FemModelSpecReadinessCheckStatus;
      requiredRankPerComponent: 3;
      components: FemModelSpecReadinessRigidBodyComponent[];
    };
    parallelConnectivity: {
      status: FemModelSpecReadinessCheckStatus;
      groups: FemModelSpecParallelConnectivityGroup[];
    };
  };
  issues: FemModelSpecIssue[];
}

export interface FemOpenSeesRenderRenderer {
  name: "OPENSEES_FRAME_2D_V1";
  version: "1.0";
}

export interface FemOpenSeesRenderInput {
  modelSpecFingerprint: string;
  readinessProfile: "FRAME_2D_ELASTIC_READINESS_V1";
  units: FemModelSpecUnits;
}

export interface FemOpenSeesRenderMapping {
  nodeTagPolicy: "IDENTITY";
  elementTagPolicy: "IDENTITY";
  geomTransfTag: 1;
  nodeCount: number;
  elementCount: number;
}

export interface FemOpenSeesRenderArtifacts {
  modelPath: string;
  modelSha256: string;
  manifestPath: string;
}

export interface FemOpenSeesRenderedResult {
  schema: "FEMAGENT_OPENSEES_RENDER_V1";
  status: "RENDERED";
  renderId: string;
  renderer: FemOpenSeesRenderRenderer;
  input: FemOpenSeesRenderInput;
  mapping: FemOpenSeesRenderMapping;
  artifacts: FemOpenSeesRenderArtifacts;
  renderFingerprint: string;
}

export interface FemOpenSeesBlockedRenderResult {
  schema: "FEMAGENT_OPENSEES_RENDER_V1";
  status: "BLOCKED";
  reason: "MODEL_NOT_READY";
  readiness: FemModelSpecReadiness;
  renderId: null;
  artifacts: null;
  renderFingerprint: null;
}

export type FemOpenSeesRenderResult = FemOpenSeesRenderedResult | FemOpenSeesBlockedRenderResult;


export interface FemAnsysRenderRenderer {
  name: "ANSYS_FRAME_2D_BEAM3_V1";
  version: "1.0";
  elementMapping: "BEAM3_PLANAR_EULER_BERNOULLI";
  massMapping: "MASS21_EXPLICIT_MASSX_MASSY";
}

export interface FemAnsysAuxiliaryMassMapping {
  nodeId: number;
  elementId: number;
  realConstantId: number;
}

export interface FemAnsysRenderMapping {
  nodeTagPolicy: "IDENTITY";
  frameElementTagPolicy: "IDENTITY";
  materialIdPolicy: "IDENTITY";
  sectionRealConstantIdPolicy: "IDENTITY";
  frameElementTypeId: 1;
  massElementTypeId: 2 | null;
  auxiliaryMassElements: FemAnsysAuxiliaryMassMapping[];
  nodeCount: number;
  frameElementCount: number;
}

export interface FemAnsysRenderArtifacts {
  modelPath: string;
  modelSha256: string;
  bundleFingerprint: string;
  manifestPath: string;
}

export interface FemAnsysRenderedResult {
  schema: "FEMAGENT_ANSYS_MODEL_RENDER_V1";
  status: "RENDERED";
  renderId: string;
  renderer: FemAnsysRenderRenderer;
  input: {
    modelSpecFingerprint: string;
    readinessProfile: "FRAME_2D_ELASTIC_READINESS_V1";
    units: FemModelSpecUnits;
    normalizedModelSpec: FemEngineeringModelSpecInput;
  };
  mapping: FemAnsysRenderMapping;
  executionScaffold: {
    profile: "ANSYS_TRANSIENT_INJECTION_HOOK_V1";
    analysisCommand: "ANTYPE,TRANS";
    solveCommand: "SOLVE";
    ownsLoad: false;
    ownsDamping: false;
    ownsTimeControls: false;
  };
  artifacts: FemAnsysRenderArtifacts;
  renderFingerprint: string;
}

export interface FemAnsysBlockedRenderResult {
  schema: "FEMAGENT_ANSYS_MODEL_RENDER_V1";
  status: "BLOCKED";
  reason: "MODEL_NOT_READY";
  readiness: FemModelSpecReadiness;
  renderId: null;
  artifacts: null;
  renderFingerprint: null;
}

export type FemAnsysRenderResult =
  | FemAnsysRenderedResult
  | FemAnsysBlockedRenderResult;
