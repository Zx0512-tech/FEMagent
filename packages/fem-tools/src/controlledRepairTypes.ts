import type {
  FemEarthquakeWorkflowPreparation,
  FemEarthquakeWorkflowPrepareInput,
} from "./earthquakeWorkflowTypes.js";
import type { FemEngineeringModelSpecInput } from "./modelSpecTypes.js";

export type FemControlledRepairPlanStatus =
  | "NO_REPAIR_NEEDED"
  | "USER_ACTION_REQUIRED"
  | "OPERATOR_ACTION_REQUIRED"
  | "MANUAL_ENGINEERING_CHANGE_REQUIRED"
  | "UNSUPPORTED_FAILURE";

export type FemControlledRepairCategory =
  | "USER_INPUT"
  | "OPERATOR_ACTION"
  | "MANUAL_ENGINEERING_CHANGE";

export interface FemControlledRepairAction {
  actionId: string;
  category: FemControlledRepairCategory;
  subject: string;
  message: string;
  resolutionTypes: string[];
  details?: Record<string, unknown>;
}

export interface FemControlledRepairPlan {
  schema: "FEMAGENT_CONTROLLED_REPAIR_PLAN_V1";
  status: FemControlledRepairPlanStatus;
  inputFingerprint: string;
  failureFingerprint: string;
  actionFingerprint: string;
  planFingerprint: string;
  actions: FemControlledRepairAction[];
  rules: {
    solverExecutionAllowed: false;
    sourceFileMutationAllowed: false;
    engineeringFactInferenceAllowed: false;
    userConfirmationRequiredForResolution: true;
  };
}

interface FemRepairEvidenceResolution {
  actionId: string;
  sourceText: string;
  quote: string;
}

export type FemControlledRepairResolution =
  | (FemRepairEvidenceResolution & { type: "ADD_DAMPING_NONE" })
  | (FemRepairEvidenceResolution & {
      type: "ADD_RAYLEIGH_DAMPING";
      alphaM: number;
      betaK: number;
    })
  | (FemRepairEvidenceResolution & {
      type: "SET_EXCITATION_COMPONENT";
      component: "X" | "Y";
    })
  | (FemRepairEvidenceResolution & { type: "ADD_LOAD_SELECTION" })
  | (FemRepairEvidenceResolution & {
      type: "SET_RESULT_COMPONENT";
      component: "X" | "Y";
    })
  | {
      actionId: string;
      type: "SET_ANSYS_MODEL_PATH";
      solverModelPath: string;
    }
  | {
      actionId: string;
      type: "REPLACE_LOAD_ARTIFACT";
      loadArtifactPath: string;
    }
  | {
      actionId: string;
      type: "REPLACE_MODEL_SPEC";
      modelSpec: FemEngineeringModelSpecInput;
    }
  | {
      actionId: string;
      type: "PROVIDE_SEMANTIC_CONTEXT";
      semanticContext: { modelPath: string; manifestPath: string };
    };

export interface FemControlledRepairRetry {
  schema: "FEMAGENT_CONTROLLED_REPAIR_RETRY_V1";
  status: "RECOVERED_TO_READY" | "RETRY_STILL_BLOCKED";
  repairPlan: FemControlledRepairPlan;
  appliedResolutions: Array<{
    actionId: string;
    type: string;
    source: "USER_CONFIRMED";
  }>;
  workflowInput: FemEarthquakeWorkflowPrepareInput;
  preparation: FemEarthquakeWorkflowPreparation;
}
