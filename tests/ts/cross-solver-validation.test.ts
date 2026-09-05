import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { runFemCrossSolverValidation, runFemModelInspect } from "@femagent/fem-tools";

const cwd = process.cwd();

function sha256(content: string): string {
  return createHash("sha256").update(content).digest("hex");
}

async function createSide(prefix: string, nodeId: number, peak: number) {
  const token = randomUUID().replaceAll("-", "").slice(0, 10);
  const relativeRoot = path.posix.join(".femagent", "cross-solver-tests", `${prefix}-${token}`);
  const root = path.join(cwd, relativeRoot);
  await mkdir(root, { recursive: true });
  const modelPath = path.posix.join(relativeRoot, "model.py");
  await writeFile(
    path.join(cwd, modelPath),
    [
      "import openseespy.opensees as ops",
      "ops.model('basic', '-ndm', 1, '-ndf', 1)",
      "ops.node(1, 0.0)",
      `ops.node(${nodeId}, 1.0)`,
      "ops.uniaxialMaterial('Elastic', 1, 100.0)",
      `ops.element('truss', 1, 1, ${nodeId}, 1.0, 1)`,
      "",
    ].join("\n"),
    "utf8",
  );
  const inspection = await runFemModelInspect(cwd, modelPath);
  if (inspection.format !== "OPENSEES_PYTHON") throw new Error("expected OpenSees model");
  const fingerprint = inspection.bundle.bundleFingerprint;
  const manifestPath = path.posix.join(relativeRoot, "semantic-roles.json");
  await writeFile(
    path.join(cwd, manifestPath),
    JSON.stringify({
      schemaVersion: "1.0",
      kind: "engineering_semantic_roles",
      model: { bundleFingerprint: fingerprint },
      roles: [{ roleId: "TOWER_BASE_LEFT", roleType: "TOWER_BASE", entity: { type: "NODE", id: nodeId } }],
    }),
    "utf8",
  );
  const runId = `run_cross${prefix}${token}`;
  const relativeRunDir = path.posix.join(".femagent", "runs", runId);
  const runDir = path.join(cwd, relativeRunDir);
  await mkdir(runDir, { recursive: true });
  const response = [
    "time_s,relative_displacement_m,relative_velocity_m_s,relative_acceleration_m_s2",
    "0,0,0,0",
    `0.1,${peak},0.2,1`,
    `0.2,${-peak / 2},-0.1,-0.5`,
    "",
  ].join("\n");
  const summaryObject = { responseNode: nodeId, responseDof: 1, sampleCount: 3, absolutePeakDisplacementM: peak };
  const summary = JSON.stringify(summaryObject);
  const solverLog = "cross solver bridge test\n";
  await writeFile(path.join(runDir, "response.csv"), response, "utf8");
  await writeFile(path.join(runDir, "result_summary.json"), summary, "utf8");
  await writeFile(path.join(runDir, "solver.log"), solverLog, "utf8");
  await writeFile(
    path.join(runDir, "run_manifest.json"),
    JSON.stringify({
      schemaVersion: "1.0",
      kind: "solver_run",
      runId,
      caseFingerprint: (prefix === "left" ? "a" : "b").repeat(64),
      status: "COMPLETED",
      solver: { name: "OPENSEESPY", packageVersion: "3.8.0.0", engineVersion: "3.8.0", executionMode: "ISOLATED_WORKER_PROCESS" },
      model: { path: modelPath, sha256: "c".repeat(64), bundleFingerprint: fingerprint },
      load: { mode: "MODEL_SCRIPT_MANAGED" },
      analysis: { type: "TRANSIENT_UNIFORM_EXCITATION" },
      summary: summaryObject,
      outputs: {
        runManifest: path.posix.join(relativeRunDir, "run_manifest.json"),
        responseCsv: path.posix.join(relativeRunDir, "response.csv"),
        responseSha256: sha256(response),
        resultSummary: path.posix.join(relativeRunDir, "result_summary.json"),
        resultSummarySha256: sha256(summary),
        solverLog: path.posix.join(relativeRunDir, "solver.log"),
        solverLogSha256: sha256(solverLog),
      },
    }),
    "utf8",
  );
  return { root, modelPath, manifestPath, runId };
}

async function cleanupSide(side: Awaited<ReturnType<typeof createSide>>) {
  await rm(side.root, { recursive: true, force: true });
  await rm(path.join(cwd, ".femagent", "runs", side.runId), { recursive: true, force: true });
}

test("cross-solver validation crosses the strict read-only bridge", async () => {
  const left = await createSide("left", 2, 0.031);
  const right = await createSide("right", 3, 0.030);
  try {
    const report = await runFemCrossSolverValidation(
      cwd,
      "bridge-demo",
      { modelPath: left.modelPath, manifestPath: left.manifestPath, roleId: "TOWER_BASE_LEFT", runRef: left.runId },
      { modelPath: right.modelPath, manifestPath: right.manifestPath, roleId: "TOWER_BASE_LEFT", runRef: right.runId },
      { quantity: "DISPLACEMENT", component: "X", operation: "SUMMARY" },
    );
    assert.equal(report.status, "COMPARABLE");
    assert.equal(report.comparison?.metric, "absolutePeak");
    assert.equal(report.sides.left?.entity?.id, 2);
    assert.equal(report.sides.right?.entity?.id, 3);
  } finally {
    await cleanupSide(left);
    await cleanupSide(right);
  }
});

test("cross-solver SERIES request returns a limitation without touching side paths", async () => {
  const report = await runFemCrossSolverValidation(
    cwd,
    "bridge-demo",
    { modelPath: "missing-left.py", manifestPath: "missing-left.json", roleId: "TOWER_BASE_LEFT", runRef: "run_missing_left" },
    { modelPath: "missing-right.py", manifestPath: "missing-right.json", roleId: "TOWER_BASE_LEFT", runRef: "run_missing_right" },
    { quantity: "DISPLACEMENT", component: "X", operation: "SERIES" },
  );
  assert.equal(report.status, "NOT_COMPARABLE");
  assert.equal(report.comparison, null);
  assert.equal(report.limitations[0]?.code, "CROSS_SOLVER_OPERATION_NOT_SUPPORTED");
});
