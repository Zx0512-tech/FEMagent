import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import {
  runFemEngineeringPerformanceEvaluation,
  runFemModelInspect,
  type FemEngineeringPerformanceRequest,
} from "@femagent/fem-tools";

function sha256(text: string): string {
  return createHash("sha256").update(text).digest("hex");
}

test("PR35 performance evaluation crosses the strict TypeScript/Python bridge", async () => {
  const cwd = await mkdtemp(path.join(tmpdir(), "femagent-pr35-"));
  const model = [
    "import openseespy.opensees as ops",
    "ops.model('basic', '-ndm', 2, '-ndf', 3)",
    "ops.node(1, 0.0, 0.0)",
    "ops.node(2, 1.0, 0.0)",
    "ops.geomTransf('Linear', 1)",
    "ops.element('elasticBeamColumn', 42, 1, 2, 0.02, 2.0e11, 8.0e-5, 1)",
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
          roleId: "GIRDER_END_RIGHT",
          roleType: "GIRDER_END",
          entity: { type: "NODE", id: 2 },
        },
        {
          roleId: "DAMPER_DEVICE",
          roleType: "DAMPER_ATTACHMENT",
          entity: { type: "ELEMENT", id: 42 },
        },
      ],
    }),
    "utf8",
  );

  const runId = "run_pr35_tsbridge1";
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
        channelId: "damper_force",
        quantity: "DAMPER_RESPONSE",
        target: { type: "ELEMENT", id: 42 },
        component: "FORCE",
        unit: "N",
        referenceFrame: "ELEMENT_LOCAL",
        abscissaSemantic: "TIME",
        abscissaUnit: "s",
        abscissaValues: [0, 0.1, 0.2],
        values: [0, 120, -150],
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
      caseFingerprint: "e".repeat(64),
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

  const request: FemEngineeringPerformanceRequest = {
    schema: "FEMAGENT_ENGINEERING_PERFORMANCE_REQUEST_V1",
    metricsRequest: {
      schema: "FEMAGENT_ENGINEERING_RESPONSE_METRIC_REQUEST_V1",
      runRef: runId,
      modelPath: "model.py",
      semanticManifestPath: "semantic.json",
      metrics: [
        {
          metricId: "girder_disp",
          type: "ROLE_ABSOLUTE_PEAK",
          roleId: "GIRDER_END_RIGHT",
          quantity: "DISPLACEMENT",
          component: "X",
        },
        {
          metricId: "damper_force",
          type: "ROLE_ABSOLUTE_PEAK",
          roleId: "DAMPER_DEVICE",
          quantity: "DAMPER_RESPONSE",
          component: "FORCE",
        },
      ],
    },
    constraints: [
      {
        constraintId: "girder_limit",
        metricId: "girder_disp",
        operator: "MAXIMUM",
        limit: 0.04,
        unit: "m",
      },
      {
        constraintId: "damper_force_limit",
        metricId: "damper_force",
        operator: "MAXIMUM",
        limit: 160,
        unit: "N",
      },
    ],
  };

  const report = await runFemEngineeringPerformanceEvaluation(cwd, request);

  assert.equal(report.status, "FEASIBLE");
  assert.equal(report.summary.satisfied, 2);
  assert.equal(report.summary.violated, 0);
  assert.equal(report.summary.notEvaluable, 0);
  assert.equal(report.governingConstraint?.constraintId, "damper_force_limit");
  assert.match(report.constraintSetFingerprint, /^[0-9a-f]{64}$/);
  assert.match(report.evaluationFingerprint, /^[0-9a-f]{64}$/);
});

test("PR35 Agent surface forbids limit inference and solver execution shortcuts", async () => {
  const extension = await readFile(
    ".pi/extensions/performance-constraint-tools.ts",
    "utf8",
  );
  const main = await readFile("apps/agent/src/main.ts", "utf8");

  assert.match(extension, /fem_performance_evaluate/);
  assert.match(extension, /Never invent a code limit/i);
  assert.match(extension, /no unit conversion/i);
  assert.match(extension, /never calls fem_solver_run/i);
  assert.doesNotMatch(extension, /runFemSolverRun/);
  assert.match(extension, /FEASIBLE means only/i);
  assert.match(main, /performance-constraint-tools\.ts/);
  assert.match(main, /"fem_performance_evaluate"/);
});
