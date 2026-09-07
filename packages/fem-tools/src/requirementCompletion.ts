import { runFemCoreRequest } from "./pythonBridge.js";
import type {
  FemEngineeringRequirementCompletion,
  FemEngineeringRequirementDraft,
} from "./requirementTypes.js";

export async function runFemRequirementComplete(
  cwd: string,
  draft: FemEngineeringRequirementDraft,
  signal?: AbortSignal,
): Promise<FemEngineeringRequirementCompletion> {
  return await runFemCoreRequest<FemEngineeringRequirementCompletion>(
    cwd,
    "requirement.complete",
    { draft },
    { signal },
  );
}
