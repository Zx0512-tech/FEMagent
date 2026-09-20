import type {
  FemEngineeringPerformanceEvaluation,
  FemEngineeringPerformanceRequest,
} from "./performanceConstraintTypes.js";
import { runFemCoreRequest } from "./pythonBridge.js";

export async function runFemEngineeringPerformanceEvaluation(
  cwd: string,
  request: FemEngineeringPerformanceRequest,
  signal?: AbortSignal,
): Promise<FemEngineeringPerformanceEvaluation> {
  return await runFemCoreRequest<FemEngineeringPerformanceEvaluation>(
    cwd,
    "performance.evaluate",
    { request },
    { signal },
  );
}
