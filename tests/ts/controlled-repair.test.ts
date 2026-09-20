import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import {
  runFemControlledRepairPlan,
  runFemControlledRepairRetry,
  runFemEarthquakeWorkflowPrepare,
  type FemEarthquakeWorkflowPrepareInput,
  type FemEngineeringAnalysisRequirementDraft,
  type FemEngineeringModelSpecInput,
} from "@femagent/fem-tools";

const HEADER =
  "time_s,load_kind,channel_id,application_type,target_type,target_id,component,quantity,value,unit\n";

async function modelSpec(): Promise<FemEngineeringModelSpecInput> {
  const model = JSON.parse(
    await readFile("tests/fixtures/model_spec/simple-portal-frame.json", "utf8"),
  ) as FemEngineeringModelSpecInput;
  model.nodalMasses = [{ nodeId: 3, mUX: 100, mUY: 100 }];
  return model;
}

function draftWithoutDamping(): FemEngineeringAnalysisRequirementDraft {
  return {
    schema: "FEMAGENT_ANALYSIS_REQUIREMENT_DRAFT_V1",
    profile: "TRANSIENT_UNIFORM_BASE_REQUIREMENT_V1",
    sources: [
      {
        sourceId: "s1",
        kind: "USER_MESSAGE",
        text:
          "做X向地震时程分析，使用这个地震波，查看节点3的X向位移和节点1的X向反力",
      },
    ],
    intent: {
      type: "TRANSIENT_UNIFORM_BASE",
      evidence: { sourceId: "s1", quote: "地震时程分析" },
    },
    facts: [
      {
        kind: "EXCITATION_COMPONENT",
        source: "USER_EXPLICIT",
        component: "X",
        evidence: { sourceId: "s1", quote: "X向" },
      },
      {
        kind: "LOAD_SELECTION",
        source: "USER_EXPLICIT",
        evidence: { sourceId: "s1", quote: "这个地震波" },
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
  const root = path.posix.join(".femagent", "controlled-repair-tests", token);
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

test("PR32 bridge plans and retries explicit damping without solver execution", async () => {
  await withLoad(async (loadArtifactPath) => {
    const workflowInput: FemEarthquakeWorkflowPrepareInput = {
      solver: "opensees",
      draft: draftWithoutDamping(),
      modelSpec: await modelSpec(),
      loadArtifactPath,
    };
    const failed = await runFemEarthquakeWorkflowPrepare(
      process.cwd(),
      workflowInput,
    );
    assert.equal(failed.status, "NEEDS_INPUT");

    const plan = await runFemControlledRepairPlan(
      process.cwd(),
      workflowInput,
      failed,
    );
    assert.equal(plan.status, "USER_ACTION_REQUIRED");
    assert.equal(plan.rules.solverExecutionAllowed, false);
    const action = plan.actions.find((item) => item.subject === "damping");
    assert.ok(action);

    const retry = await runFemControlledRepairRetry(
      process.cwd(),
      workflowInput,
      failed,
      plan.planFingerprint,
      [
        {
          actionId: action.actionId,
          type: "ADD_DAMPING_NONE",
          sourceText: "本次分析不考虑阻尼",
          quote: "不考虑阻尼",
        },
      ],
    );

    assert.equal(retry.status, "RECOVERED_TO_READY");
    assert.equal(retry.preparation.status, "READY_FOR_CONFIRMATION");
  });
});

test("PR32 Agent tools remain SAFE and do not expose a repair-run shortcut", async () => {
  const source = await readFile(
    ".pi/extensions/controlled-repair-tools.ts",
    "utf8",
  );
  const main = await readFile("apps/agent/src/main.ts", "utf8");

  assert.match(source, /fem_controlled_repair_plan/);
  assert.match(source, /fem_controlled_repair_retry/);
  assert.doesNotMatch(source, /runFemSolverRun/);
  assert.doesNotMatch(source, /name:\s*"fem_controlled_repair_run"/);
  assert.match(source, /never calls fem_solver_run/i);
  assert.match(main, /controlled-repair-tools\.ts/);
  assert.match(main, /"fem_controlled_repair_plan"/);
  assert.match(main, /"fem_controlled_repair_retry"/);
});
