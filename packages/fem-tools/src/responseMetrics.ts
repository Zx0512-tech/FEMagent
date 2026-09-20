import type {
  FemEngineeringResponseMetricsReport,
  FemEngineeringResponseMetricsRequest,
} from "./responseMetricTypes.js";
import { runFemCoreRequest } from "./pythonBridge.js";

export async function runFemEngineeringResponseMetrics(
  cwd: string,
  request: FemEngineeringResponseMetricsRequest,
  signal?: AbortSignal,
): Promise<FemEngineeringResponseMetricsReport> {
  return await runFemCoreRequest<FemEngineeringResponseMetricsReport>(
    cwd,
    "responseMetrics.compute",
    { request },
    { signal },
  );
}
