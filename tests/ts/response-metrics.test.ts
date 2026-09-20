import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import {
  runFemEngineeringResponseMetrics,
  runFemModelInspect,
  type FemEngineeringResponseMetricsRequest,
} from "@femagent/fem-tools";

function sha256(text: string): string {
  return createHash("sha256").update(text).digest("hex");
}

test("PR34 response metrics cross the strict TypeScript/Python bridge", async () => {
  const cwd = await mkdtemp(path.join(tmpdir(), "femagent-pr34-"));
  const model = [
    "import openseespy.opensees as ops",
    "ops.model('basic', '-ndm', 2, '-ndf', 3)",
    "ops.node(1, 0.0, 0.0)",
    "ops.node(2, 1.0, 0.0)",
    "ops.geomTransf('Linear', 1)",
    "ops.element('elasticBeamColumn', 41, 1, 2, 0.02, 2.0e11, 8.0e-5, 1)",
    "",
  ].join("\n");
  await writeFile(path.join(cwd, "model.py"), model, "utf8");

  const inspection = await runFemModelInspect(cwd, "model.py");
  const bundle = (inspection as unknown as {
    bundle: { bundleFingerprint: string };
  }).bundle.bundleFingerprint;

  await writeFile(
    path.join(cwd, "semantic.json"),
    JSON.stringify({
      schemaVersion: "1.0",
      kind: "engineering_semantic_roles",
      model: { bundleFingerprint: bundle },
      roles: [
        {
          roleId: "SUPPORT_LEFT",
          roleType: "SUPPORT",
          entity: { type: "NODE", id: 1 },
        },
        {
          roleId: "GIRDER_END_RIGHT",
          roleType: "GIRDER_END",
          entity: { type: "NODE", id: 2 },
        },
      ],
    }),
    "utf8",
  );

  const runId = "run_pr34_tsbridge1";
  const runDir = path.join(cwd, ".femagent", "runs", runId);
  await mkdir(runDir, { recursive: true });
  const structural = JSON.stringify({
    schemaVersion: "1.0",
    kind: "structural_response_series",
    channels: [
      {
        channelId: "u2x",
        quantity: "DISPLACEMENT",
        target: { type: "NODE", id: 2 },
        component: "X",
        unit: "m",
        referenceFrame: "GLOBAL",
        abscissaSemantic: "TIME",
        abscissaUnit: "s",
        abscissaValues: [0, 0.1, 0.2],
        values: [0, 0.02, -0.03],
      },
      {
        channelId: "r1x",
        quantity: "REACTION_FORCE",
        target: { type: "NODE", id: 1 },
        component: "X",
        unit: "N",
        referenceFrame: "GLOBAL",
        abscissaSemantic: "TIME",
        abscissaUnit: "s",
        abscissaValues: [0, 0.1, 0.2],
        values: [0, 3, 4],
      },
      {
        channelId: "r1y",
        quantity: "REACTION_FORCE",
        target: { type: "NODE", id: 1 },
        component: "Y",
        unit: "N",
        referenceFrame: "GLOBAL",
        abscissaSemantic: "TIME",
        abscissaUnit: "s",
        abscissaValues: [0, 0.1, 0.2],
        values: [0, 4, 3],
      },
    ],
  });
  await writeFile(
    path.join(runDir, "structural_response.json"),
    structural,
    "utf8",
  );
  await writeFile(
    path.join(runDir, "run_manifest.json"),
    JSON.stringify({
      schemaVersion: "1.0",
      kind: "solver_run",
      runId,
      caseFingerprint: "a".repeat(64),
      status: "COMPLETED",
      solver: {
        name: "OPENSEESPY",
        executionMode: "ISOLATED_WORKER_PROCESS",
      },
      model: { path: "model.py", bundleFingerprint: bundle },
      load: { mode: "MODEL_SCRIPT_MANAGED" },
      analysis: { type: "TRANSIENT" },
      summary: {},
      outputs: {
        runManifest: `.femagent/runs/${runId}/run_manifest.json`,
        structuralResponse:
          `.femagent/runs/${runId}/structural_response.json`,
        structuralResponseSha256: sha256(structural),
      },
    }),
    "utf8",
  );

  const request: FemEngineeringResponseMetricsRequest = {
    schema: "FEMAGENT_ENGINEERING_RESPONSE_METRIC_REQUEST_V1",
    runRef: runId,
    modelPath: "model.py",
    semanticManifestPath: "semantic.json",
    metrics: [
      {
        metricId: "girder_peak",
        type: "ROLE_ABSOLUTE_PEAK",
        roleId: "GIRDER_END_RIGHT",
        quantity: "DISPLACEMENT",
        component: "X",
      },
      {
        metricId: "support_resultant",
        type: "ROLE_GROUP_REACTION_RESULTANT_PEAK",
        roleIds: ["SUPPORT_LEFT"],
        components: ["X", "Y"],
      },
    ],
  };

  const report = await runFemEngineeringResponseMetrics(cwd, request);

  assert.equal(report.status, "COMPLETED");
  assert.equal(report.metrics.length, 2);
  const byId = new Map(report.metrics.map((item) => [item.metricId, item]));
  assert.equal(byId.get("girder_peak")?.absolutePeak, 0.03);
  assert.equal(byId.get("support_resultant")?.absolutePeak, 5);
  assert.equal(report.run.modelBundleFingerprint, bundle);
});

test("PR34 Agent surface is SAFE and does not expose a solver shortcut", async () => {
  const extension = await readFile(
    ".pi/extensions/response-metric-tools.ts",
    "utf8",
  );
  const main = await readFile("apps/agent/src/main.ts", "utf8");

  assert.match(extension, /fem_response_metrics_compute/);
  assert.match(extension, /never calls fem_solver_run/i);
  assert.doesNotMatch(extension, /runFemSolverRun/);
  assert.match(extension, /SIGNED_COMPONENT_SUM_THEN_VECTOR_MAGNITUDE/);
  assert.match(main, /response-metric-tools\.ts/);
  assert.match(main, /"fem_response_metrics_compute"/);
});
