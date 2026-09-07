import type {
  FemEngineeringModelSpecInput,
  FemModelSpecDof,
  FemModelSpecForceUnit,
  FemModelSpecLengthUnit,
  FemModelSpecTimeUnit,
  FemModelSpecValidation,
} from "./modelSpecTypes.js";

export type FemRequirementCompletionStatus =
  | "COMPLETE"
  | "INCOMPLETE"
  | "CONFLICT"
  | "INVALID_DRAFT";

export type FemRequirementTemplateId =
  | "SIMPLY_SUPPORTED_BEAM_2D_V1"
  | "CANTILEVER_BEAM_2D_V1"
  | "FIXED_FIXED_BEAM_2D_V1";

export interface FemRequirementEvidence {
  sourceId: string;
  quote: string;
}

export interface FemRequirementSource {
  sourceId: string;
  kind: "USER_MESSAGE";
  text: string;
}

export interface FemTemplateIntent {
  templateId: FemRequirementTemplateId;
  evidence: FemRequirementEvidence;
}

interface FemExplicitFactBase {
  source: "USER_EXPLICIT";
  evidence: FemRequirementEvidence;
}

export interface FemSpanRequirementFact extends FemExplicitFactBase {
  kind: "SPAN";
  value: number;
  unit: FemModelSpecLengthUnit;
}

export type FemUnitDeclarationRequirementFact =
  | (FemExplicitFactBase & {
      kind: "UNIT_DECLARATION";
      dimension: "length";
      value: FemModelSpecLengthUnit;
    })
  | (FemExplicitFactBase & {
      kind: "UNIT_DECLARATION";
      dimension: "force";
      value: FemModelSpecForceUnit;
    })
  | (FemExplicitFactBase & {
      kind: "UNIT_DECLARATION";
      dimension: "time";
      value: FemModelSpecTimeUnit;
    });

export interface FemYoungsModulusRequirementFact extends FemExplicitFactBase {
  kind: "YOUNGS_MODULUS";
  value: number;
  unit:
    | "Pa"
    | "N/m²"
    | "N/cm²"
    | "N/mm²"
    | "kN/m²"
    | "kN/cm²"
    | "kN/mm²";
  materialId?: number;
}

export interface FemSectionAreaRequirementFact extends FemExplicitFactBase {
  kind: "SECTION_AREA";
  value: number;
  unit: "m²" | "cm²" | "mm²";
  sectionId?: number;
}

export interface FemSectionIzRequirementFact extends FemExplicitFactBase {
  kind: "SECTION_IZ";
  value: number;
  unit: "m⁴" | "cm⁴" | "mm⁴";
  sectionId?: number;
}

export interface FemNodeCoordinateRequirementFact extends FemExplicitFactBase {
  kind: "NODE_COORDINATE";
  nodeId: number;
  x: number;
  y: number;
  unit: FemModelSpecLengthUnit;
}

export interface FemElementConnectivityRequirementFact extends FemExplicitFactBase {
  kind: "ELEMENT_CONNECTIVITY";
  elementId: number;
  nodeI: number;
  nodeJ: number;
}

export interface FemElementMaterialRefRequirementFact extends FemExplicitFactBase {
  kind: "ELEMENT_MATERIAL_REF";
  elementId: number;
  materialId: number;
}

export interface FemElementSectionRefRequirementFact extends FemExplicitFactBase {
  kind: "ELEMENT_SECTION_REF";
  elementId: number;
  sectionId: number;
}

export interface FemNodeConstraintRequirementFact extends FemExplicitFactBase {
  kind: "NODE_CONSTRAINT";
  nodeId: number;
  dofs: FemModelSpecDof[];
}

export interface FemNodalMassRequirementFact extends FemExplicitFactBase {
  kind: "NODAL_MASS";
  nodeId: number;
  mUX: number;
  mUY: number;
}

export type FemRequirementFact =
  | FemSpanRequirementFact
  | FemUnitDeclarationRequirementFact
  | FemYoungsModulusRequirementFact
  | FemSectionAreaRequirementFact
  | FemSectionIzRequirementFact
  | FemNodeCoordinateRequirementFact
  | FemElementConnectivityRequirementFact
  | FemElementMaterialRefRequirementFact
  | FemElementSectionRefRequirementFact
  | FemNodeConstraintRequirementFact
  | FemNodalMassRequirementFact;

export interface FemEngineeringRequirementDraft {
  schema: "FEMAGENT_ENGINEERING_REQUIREMENT_DRAFT_V1";
  profile: "FRAME_2D_REQUIREMENT_V1";
  sources: FemRequirementSource[];
  templateIntent: FemTemplateIntent | null;
  facts: FemRequirementFact[];
}

export interface FemRequirementIssue {
  severity: "ERROR" | "WARNING";
  code: string;
  path: string;
  message: string;
}

export interface FemRequirementGap {
  code: string;
  subject: string;
  message: string;
}

export interface FemRequirementDerivedFact {
  kind: string;
  source: "TEMPLATE_DERIVED" | "DETERMINISTIC_DERIVED";
  [key: string]: unknown;
}

export interface FemEngineeringRequirementCompletion {
  schema: "FEMAGENT_ENGINEERING_REQUIREMENT_COMPLETION_V1";
  profile: "FRAME_2D_REQUIREMENT_V1";
  status: FemRequirementCompletionStatus;
  acceptedFacts: FemRequirementFact[];
  derivedFacts: FemRequirementDerivedFact[];
  template: FemTemplateIntent | null;
  issues: FemRequirementIssue[];
  missing: FemRequirementGap[];
  ambiguous: FemRequirementGap[];
  conflicts: FemRequirementGap[];
  candidateModelSpec: FemEngineeringModelSpecInput | null;
  modelSpecValidation: FemModelSpecValidation | null;
  modelSpecFingerprint: string | null;
  requirementFingerprint: string | null;
}
