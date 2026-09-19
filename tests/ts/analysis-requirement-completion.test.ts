import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import {
  runFemAnalysisRequirementComplete,
  type FemEngineeringAnalysisRequirementDraft,
  type FemEngineeringModelSpecInput,
} from "@femagent/fem-tools";

const HEADER =
  "time_s,load_kind,channel_id,application_type,target_type,target_id,component,quantity,value,unit\n";

async function modelSpec(): Promise<FemEngineeringModelSpecInput> {
  return JSON.parse(
    await readFile("tests/fixtures/model_spec/simple-portal-frame.json", "utf8"),
  ) as FemEngineeringModelSpecInput;
}

function draft(includeDamping = true): FemEngineeringAnalysisRequirementDraft {
  const facts: FemEngineeringAnalysisRequirementDraft["facts"] = [
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
  ];
  if (includeDamping) {
    facts.splice(2, 0, {
      kind: "DAMPING_NONE",
      source: "USER_EXPLICIT",
      evidence: { sourceId: "s1", quote: "不考虑阻尼" },
    });
  }
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
    facts,
  };
}

async function withCanonicalLoad(
  fn: (loadPath: string) => Promise<void>,
): Promise<void> {
  const token = randomUUID().replaceAll("-", "").slice(0, 12);
  const root = path.posix.join(".femagent", "analysis-requirement-tests", token);
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

test("PR30 completion crosses the TypeScript/Python bridge and derives time/load identity", async () => {
  await withCanonicalLoad(async (loadPath) => {
    const result = await runFemAnalysisRequirementComplete(
      process.cwd(),
      draft(),
      await modelSpec(),
      loadPath,
    );

    assert.equal(result.schema, "FEMAGENT_ANALYSIS_REQUIREMENT_COMPLETION_V1");
    assert.equal(result.status, "COMPLETE");
    assert.equal(result.candidateAnalysisSpec?.analysisType, "TRANSIENT");
    assert.deepEqual(result.candidateAnalysisSpec?.definition.time, {
      timeStep: 0.01,
      duration: 0.02,
    });
    assert.equal(
      result.candidateAnalysisSpec?.definition.excitation.loadArtifact.path,
      loadPath,
    );
    assert.match(
      result.candidateAnalysisSpec?.definition.excitation.loadArtifact.sha256 ?? "",
      /^[0-9a-f]{64}$/,
    );
  });
});

test("PR30 bridge preserves missing damping instead of defaulting it", async () => {
  await withCanonicalLoad(async (loadPath) => {
    const result = await runFemAnalysisRequirementComplete(
      process.cwd(),
      draft(false),
      await modelSpec(),
      loadPath,
    );

    assert.equal(result.status, "INCOMPLETE");
    assert.equal(result.candidateAnalysisSpec, null);
    assert.ok(result.missing.some((item) => item.subject === "damping"));
  });
});

test("PR30 exposes one SAFE analysis completion tool and no execution shortcut", async () => {
  const extension = await readFile(
    ".pi/extensions/analysis-requirement-tools.ts",
    "utf8",
  );
  const main = await readFile("apps/agent/src/main.ts", "utf8");

  assert.match(extension, /name:\s*"fem_analysis_requirement_complete"/);
  assert.match(extension, /SAFE and read-only/i);
  assert.match(extension, /never call OpenSees or ANSYS execution/i);
  assert.doesNotMatch(extension, /runFemSolverRun/);
  assert.doesNotMatch(extension, /runFemAnalysisRenderOpenSees/);
  assert.match(main, /analysis-requirement-tools\.ts/);
  assert.match(main, /"fem_analysis_requirement_complete"/);
});
