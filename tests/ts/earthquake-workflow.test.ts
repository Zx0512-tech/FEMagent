import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import {
  FemCoreError,
  runFemEarthquakeWorkflowPrepare,
  runFemEarthquakeWorkflowSummarize,
  type FemEarthquakeWorkflowPrepareInput,
  type FemEngineeringAnalysisRequirementDraft,
  type FemEngineeringModelSpecInput,
} from "@femagent/fem-tools";

const HEADER =
  "time_s,load_kind,channel_id,application_type,target_type,target_id,component,quantity,value,unit\n";

async function modelSpec(withMass = true): Promise<FemEngineeringModelSpecInput> {
  const model = JSON.parse(
    await readFile("tests/fixtures/model_spec/simple-portal-frame.json", "utf8"),
  ) as FemEngineeringModelSpecInput;
  model.nodalMasses = withMass
    ? [{ nodeId: 3, mUX: 100, mUY: 100 }]
    : [];
  return model;
}

function draft(): FemEngineeringAnalysisRequirementDraft {
  return {
    schema: "FEMAGENT_ANALYSIS_REQUIREMENT_DRAFT_V1",
    profile: "TRANSIENT_UNIFORM_BASE_REQUIREMENT_V1",
    sources: [
      {
        sourceId: "s1",
        kind: "USER_MESSAGE",
        text:
          "对模型做X向地震时程分析，使用这个地震波，不考虑阻尼，查看节点3的X向位移和节点1的X向反力",
      },
    ],
    intent: {
      type: "TRANSIENT_UNIFORM_BASE",
      evidence: { sourceId: "s1", quote: "X向地震时程分析" },
    },
    facts: [
      {
        kind: "EXCITATION_COMPONENT",
        source: "USER_EXPLICIT",
        component: "X",
        evidence: { sourceId: "s1", quote: "X向地震时程分析" },
      },
      {
        kind: "LOAD_SELECTION",
        source: "USER_EXPLICIT",
        evidence: { sourceId: "s1", quote: "这个地震波" },
      },
      {
        kind: "DAMPING_NONE",
        source: "USER_EXPLICIT",
        evidence: { sourceId: "s1", quote: "不考虑阻尼" },
      },
      {
        kind: "RESULT_REQUEST",
        source: "USER_EXPLICIT",
        quantity: "DISPLACEMENT",
        target: { type: "NODE", id: 3 },
        component: "X",
        evidence: { sourceId: "s1", quote: "节点3的X向位移" },
      },
      {
        kind: "RESULT_REQUEST",
        source: "USER_EXPLICIT",
        quantity: "REACTION_FORCE",
        target: { type: "NODE", id: 1 },
        component: "X",
        evidence: { sourceId: "s1", quote: "节点1的X向反力" },
      },
    ],
  };
}

async function withLoad(
  fn: (loadPath: string) => Promise<void>,
): Promise<void> {
  const token = randomUUID().replaceAll("-", "").slice(0, 12);
  const root = path.posix.join(".femagent", "workflow-tests", token);
  const loadPath = path.posix.join(root, "earthquake.csv");
  await mkdir(root, { recursive: true });
  await writeFile(
    loadPath,
    HEADER
      + "0,EARTHQUAKE,EQ,UNIFORM_EXCITATION,,,X,ACCELERATION,0,m/s2\n"
      + "0.01,EARTHQUAKE,EQ,UNIFORM_EXCITATION,,,X,ACCELERATION,1,m/s2\n"
      + "0.02,EARTHQUAKE,EQ,UNIFORM_EXCITATION,,,X,ACCELERATION,0,m/s2\n",
    "utf8",
  );
  try {
    await fn(loadPath);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

test("PR31 TypeScript bridge prepares an exact OpenSees run handoff", async () => {
  await withLoad(async (loadArtifactPath) => {
    const input: FemEarthquakeWorkflowPrepareInput = {
      solver: "opensees",
      draft: draft(),
      modelSpec: await modelSpec(),
      loadArtifactPath,
    };
    const result = await runFemEarthquakeWorkflowPrepare(
      process.cwd(),
      input,
    );

    assert.equal(result.status, "READY_FOR_CONFIRMATION");
    assert.equal(result.preflight?.status, "READY");
    assert.equal(result.solverRunRequest?.solver, "opensees");
    assert.equal(result.solverRunRequest?.modelPath.endsWith("/analysis.py"), true);
    assert.equal(
      typeof result.solverRunRequest?.solverOptions.responsePlanPath,
      "string",
    );
    assert.equal(
      typeof result.solverRunRequest?.solverOptions.analysisManifestPath,
      "string",
    );
    assert.match(result.workflowManifest?.sha256 ?? "", /^[0-9a-f]{64}$/);
  });
});

test("PR31 bridge refuses generated OpenSees base excitation without mass", async () => {
  await withLoad(async (loadArtifactPath) => {
    const result = await runFemEarthquakeWorkflowPrepare(
      process.cwd(),
      {
        solver: "opensees",
        draft: draft(),
        modelSpec: await modelSpec(false),
        loadArtifactPath,
      },
    );

    assert.equal(result.status, "ANALYSIS_NOT_READY");
    assert.equal(result.solverRunRequest, null);
    assert.equal(result.workflowManifest, null);
  });
});

test("PR31 adds no execution shortcut and keeps confirmation on fem_solver_run", async () => {
  const workflowTools = await readFile(
    ".pi/extensions/earthquake-workflow-tools.ts",
    "utf8",
  );
  const permissionGate = await readFile(
    ".pi/extensions/permission-gate.ts",
    "utf8",
  );
  const main = await readFile("apps/agent/src/main.ts", "utf8");

  assert.match(workflowTools, /fem_earthquake_workflow_prepare/);
  assert.match(workflowTools, /fem_earthquake_workflow_summarize/);
  assert.doesNotMatch(workflowTools, /runFemSolverRun/);
  assert.doesNotMatch(workflowTools, /name:\s*"fem_earthquake_workflow_run"/);
  assert.match(permissionGate, /event\.toolName !== "fem_solver_run"/);
  assert.match(permissionGate, /Run real FEM analysis\?/);
  assert.match(permissionGate, /analysisManifestPath/);
  assert.match(permissionGate, /confirmedBundleFingerprint/);
  assert.match(main, /earthquake-workflow-tools\.ts/);
  assert.match(main, /"fem_earthquake_workflow_prepare"/);
  assert.match(main, /"fem_earthquake_workflow_summarize"/);
});


test("PR31 summarize command crosses the TypeScript/Python bridge fail-closed", async () => {
  await assert.rejects(
    runFemEarthquakeWorkflowSummarize(
      process.cwd(),
      ".femagent/workflows/missing/workflow_manifest.json",
      "0".repeat(64),
      "run_missing",
    ),
    (error: unknown) =>
      error instanceof FemCoreError && error.code === "FILE_NOT_FOUND",
  );
});
