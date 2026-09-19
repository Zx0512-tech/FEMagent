import type {
  FemEarthquakeWorkflowPreparation,
  FemEarthquakeWorkflowPrepareInput,
  FemEarthquakeWorkflowSummary,
} from "./earthquakeWorkflowTypes.js";
import { runFemCoreRequest } from "./pythonBridge.js";

export async function runFemEarthquakeWorkflowPrepare(
  cwd: string,
  input: FemEarthquakeWorkflowPrepareInput,
  signal?: AbortSignal,
): Promise<FemEarthquakeWorkflowPreparation> {
  return await runFemCoreRequest<FemEarthquakeWorkflowPreparation>(
    cwd,
    "earthquakeWorkflow.prepare",
    {
      solver: input.solver,
      draft: input.draft,
      modelSpec: input.modelSpec,
      loadArtifactPath: input.loadArtifactPath,
      ...(input.semanticContext ? { semanticContext: input.semanticContext } : {}),
      ...(input.solverModelPath ? { solverModelPath: input.solverModelPath } : {}),
    },
    { signal },
  );
}

export async function runFemEarthquakeWorkflowSummarize(
  cwd: string,
  workflowManifestPath: string,
  workflowManifestSha256: string,
  runRef: string,
  signal?: AbortSignal,
): Promise<FemEarthquakeWorkflowSummary> {
  return await runFemCoreRequest<FemEarthquakeWorkflowSummary>(
    cwd,
    "earthquakeWorkflow.summarize",
    {
      workflowManifestPath,
      workflowManifestSha256,
      runRef,
    },
    { signal },
  );
}
