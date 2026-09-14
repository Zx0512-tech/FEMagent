export * from "./pythonBridgeLegacy.js";

import type {
  FemAnalysisReadiness,
  FemEngineeringAnalysisSpecInput,
  FemOpenSeesAnalysisRenderResult,
} from "./analysisSpecTypes.js";
import type { FemEngineeringModelSpecInput } from "./modelSpecTypes.js";
import { runFemCoreRequest } from "./pythonBridgeLegacy.js";

export async function runFemAnalysisReadiness(
  cwd: string,
  modelSpec: FemEngineeringModelSpecInput,
  analysisSpec: FemEngineeringAnalysisSpecInput,
  signal?: AbortSignal,
): Promise<FemAnalysisReadiness> {
  return await runFemCoreRequest<FemAnalysisReadiness>(
    cwd,
    "analysis.readiness",
    { modelSpec, analysisSpec },
    { signal },
  );
}

export async function runFemAnalysisRenderOpenSees(
  cwd: string,
  modelSpec: FemEngineeringModelSpecInput,
  analysisSpec: FemEngineeringAnalysisSpecInput,
  signal?: AbortSignal,
): Promise<FemOpenSeesAnalysisRenderResult> {
  return await runFemCoreRequest<FemOpenSeesAnalysisRenderResult>(
    cwd,
    "analysis.renderOpenSees",
    { modelSpec, analysisSpec },
    { signal },
  );
}
