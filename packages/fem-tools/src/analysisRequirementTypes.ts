import type {
  FemAnalysisSpecValidation,
  FemEngineeringBaseTransientAnalysisSpecV2Input,
} from "./analysisSpecTypes.js";
import type { FemEngineeringModelSpecInput } from "./modelSpecTypes.js";

export type FemAnalysisRequirementCompletionStatus =
  | "COMPLETE"
  | "INCOMPLETE"
  | "CONFLICT"
  | "INVALID_DRAFT"
  | "INVALID_CONTEXT";

export interface FemAnalysisRequirementEvidence {
  sourceId: string;
  quote: string;
}

export interface FemAnalysisRequirementSource {
  sourceId: string;
  kind: "USER_MESSAGE";
  text: string;
}

export interface FemAnalysisRequirementIntent {
  type: "TRANSIENT_UNIFORM_BASE";
  evidence: FemAnalysisRequirementEvidence;
}

interface FemAnalysisRequirementExplicitBase {
  source: "USER_EXPLICIT";
  evidence: FemAnalysisRequirementEvidence;
}

export interface FemExcitationComponentAnalysisFact
  extends FemAnalysisRequirementExplicitBase {
  kind: "EXCITATION_COMPONENT";
  component: "X" | "Y";
}

export interface FemLoadSelectionAnalysisFact
  extends FemAnalysisRequirementExplicitBase {
  kind: "LOAD_SELECTION";
}

export interface FemNoDampingAnalysisFact
  extends FemAnalysisRequirementExplicitBase {
  kind: "DAMPING_NONE";
}

export interface FemRayleighDampingAnalysisFact
  extends FemAnalysisRequirementExplicitBase {
  kind: "RAYLEIGH_DAMPING";
  alphaM: number;
  betaK: number;
}

export type FemAnalysisRequirementTarget =
  | { type: "NODE"; id: number }
  | {
      type: "SEMANTIC_ROLE_TYPE";
      roleType:
        | "GIRDER_END"
        | "TOWER_BASE"
        | "MIDSPAN"
        | "SUPPORT"
        | "BEARING"
        | "DAMPER_ATTACHMENT";
    };

export interface FemResultRequestAnalysisFact
  extends FemAnalysisRequirementExplicitBase {
  kind: "RESULT_REQUEST";
  quantity: "DISPLACEMENT" | "REACTION_FORCE";
  target: FemAnalysisRequirementTarget;
  component?: "X" | "Y";
}

export type FemAnalysisRequirementFact =
  | FemExcitationComponentAnalysisFact
  | FemLoadSelectionAnalysisFact
  | FemNoDampingAnalysisFact
  | FemRayleighDampingAnalysisFact
  | FemResultRequestAnalysisFact;

export interface FemEngineeringAnalysisRequirementDraft {
  schema: "FEMAGENT_ANALYSIS_REQUIREMENT_DRAFT_V1";
  profile: "TRANSIENT_UNIFORM_BASE_REQUIREMENT_V1";
  sources: FemAnalysisRequirementSource[];
  intent: FemAnalysisRequirementIntent;
  facts: FemAnalysisRequirementFact[];
}

export interface FemAnalysisRequirementSemanticContext {
  modelPath: string;
  manifestPath: string;
}

export interface FemAnalysisRequirementGap {
  code: string;
  subject: string;
  message: string;
  candidates?: string[];
  details?: Record<string, unknown>;
}

export interface FemAnalysisRequirementCompletion {
  schema: "FEMAGENT_ANALYSIS_REQUIREMENT_COMPLETION_V1";
  profile: "TRANSIENT_UNIFORM_BASE_REQUIREMENT_V1";
  status: FemAnalysisRequirementCompletionStatus;
  acceptedFacts: FemAnalysisRequirementFact[];
  derivedFacts: Array<Record<string, unknown>>;
  context: {
    modelSpec: {
      modelSpecFingerprint: string;
      units: FemEngineeringModelSpecInput["units"];
    } | null;
    loadArtifact: {
      path: string;
      sha256: string;
      format: string;
      sampleCount: number;
      dtS: number;
      timeStartS: number;
      timeEndS: number;
      loadKind: string;
      applicationType: string;
      component: string;
      quantity: string;
      unit: string;
      channelId: string;
    } | null;
    semantic: FemAnalysisRequirementSemanticContext | null;
  };
  issues: FemAnalysisRequirementGap[];
  missing: FemAnalysisRequirementGap[];
  ambiguous: FemAnalysisRequirementGap[];
  conflicts: FemAnalysisRequirementGap[];
  candidateAnalysisSpec: FemEngineeringBaseTransientAnalysisSpecV2Input | null;
  analysisSpecValidation: Pick<
    FemAnalysisSpecValidation,
    "schema" | "status" | "issues"
  > | null;
  analysisSpecFingerprint: string | null;
  requirementFingerprint: string | null;
}
