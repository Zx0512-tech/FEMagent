import type {
  FemAnsysRenderResult,
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


export async function runFemModelSpecRenderAnsys(
  cwd: string,
  spec: FemEngineeringModelSpecInput,
  signal?: AbortSignal,
): Promise<FemAnsysRenderResult> {
  return await runFemCoreRequest<FemAnsysRenderResult>(
    cwd,
    "modelSpec.renderAnsys",
    { spec },
    { signal },
  );
}
