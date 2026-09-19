import type {
  FemAnalysisRequirementCompletion,
  FemAnalysisRequirementSemanticContext,
  FemEngineeringAnalysisRequirementDraft,
} from "./analysisRequirementTypes.js";
import type { FemEngineeringModelSpecInput } from "./modelSpecTypes.js";
import { runFemCoreRequest } from "./pythonBridge.js";

export async function runFemAnalysisRequirementComplete(
  cwd: string,
  draft: FemEngineeringAnalysisRequirementDraft,
  modelSpec: FemEngineeringModelSpecInput,
  loadArtifactPath: string,
  semanticContext?: FemAnalysisRequirementSemanticContext,
  signal?: AbortSignal,
): Promise<FemAnalysisRequirementCompletion> {
  return await runFemCoreRequest<FemAnalysisRequirementCompletion>(
    cwd,
    "analysisRequirement.complete",
    {
      draft,
      modelSpec,
      loadArtifactPath,
      ...(semanticContext ? { semanticContext } : {}),
    },
    { signal },
  );
}
