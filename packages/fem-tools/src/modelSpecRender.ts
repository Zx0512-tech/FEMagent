import type {
  FemEngineeringModelSpecInput,
  FemOpenSeesRenderResult,
} from "./modelSpecTypes.js";
import { runFemCoreRequest } from "./pythonBridge.js";

export async function runFemModelSpecRenderOpenSees(
  cwd: string,
  spec: FemEngineeringModelSpecInput,
  signal?: AbortSignal,
): Promise<FemOpenSeesRenderResult> {
  return await runFemCoreRequest<FemOpenSeesRenderResult>(
    cwd,
    "modelSpec.renderOpenSees",
    { spec },
    { signal },
  );
}
