import type {
  FemControlledRepairPlan,
  FemControlledRepairResolution,
  FemControlledRepairRetry,
} from "./controlledRepairTypes.js";
import type {
  FemEarthquakeWorkflowPreparation,
  FemEarthquakeWorkflowPrepareInput,
} from "./earthquakeWorkflowTypes.js";
import { runFemCoreRequest } from "./pythonBridge.js";

export async function runFemControlledRepairPlan(
  cwd: string,
  workflowInput: FemEarthquakeWorkflowPrepareInput,
  failedPreparation: FemEarthquakeWorkflowPreparation,
  signal?: AbortSignal,
): Promise<FemControlledRepairPlan> {
  return await runFemCoreRequest<FemControlledRepairPlan>(
    cwd,
    "controlledRepair.plan",
    { workflowInput, failedPreparation },
    { signal },
  );
}

export async function runFemControlledRepairRetry(
  cwd: string,
  workflowInput: FemEarthquakeWorkflowPrepareInput,
  failedPreparation: FemEarthquakeWorkflowPreparation,
  planFingerprint: string,
  resolutions: FemControlledRepairResolution[],
  signal?: AbortSignal,
): Promise<FemControlledRepairRetry> {
  return await runFemCoreRequest<FemControlledRepairRetry>(
    cwd,
    "controlledRepair.retry",
    {
      workflowInput,
      failedPreparation,
      planFingerprint,
      resolutions,
    },
    { signal },
  );
}
