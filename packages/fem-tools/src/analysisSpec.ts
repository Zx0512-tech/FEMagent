import type {
  FemAnalysisSpecValidation,
  FemEngineeringAnalysisSpecInput,
} from "./analysisSpecTypes.js";
import { runFemCoreRequest } from "./pythonBridge.js";

export async function runFemAnalysisSpecValidate(
  cwd: string,
  spec: FemEngineeringAnalysisSpecInput,
  signal?: AbortSignal,
): Promise<FemAnalysisSpecValidation> {
  return await runFemCoreRequest<FemAnalysisSpecValidation>(
    cwd,
    "analysisSpec.validate",
    { spec },
    { signal },
  );
}
