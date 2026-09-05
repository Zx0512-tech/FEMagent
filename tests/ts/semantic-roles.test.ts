import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import {
  runFemModelInspect,
  runFemRoleEvidenceProject,
  runFemSemanticInspect,
  runFemSemanticResolve,
} from "@femagent/fem-tools";

const cwd = process.cwd();

function sha256(content: string): string {
  return createHash("sha256").update(content).digest("hex");
}

async function createSemanticWorkspace(): Promise<{
  root: string;
  modelPath: string;
  manifestPath: string;
  runId: string;
  fingerprint: string;
}> {
  const token = randomUUID().replaceAll("-", "").slice(0, 12);
  const relativeRoot = path.posix.join(".femagent", "semantic-tests", token);
  const root = path.join(cwd, relativeRoot);
  await mkdir(root, { recursive: true });

  const modelPath = path.posix.join(relativeRoot, "model.py");
  await writeFile(
    path.join(cwd, modelPath),
    [
      "import openseespy.opensees as ops",
      "ops.model('basic', '-ndm', 1, '-ndf', 1)",
      "ops.node(1, 0.0)",
      "ops.node(2, 1.0)",
      "ops.uniaxialMaterial('Elastic', 1, 100.0)",
      "ops.element('truss', 1, 1, 2, 1.0, 1)",
      "",
    ].join("\n"),
    "utf8",
  );
  const inspection = await runFemModelInspect(cwd, modelPath);
  const fingerprint = inspection.bundle.bundleFingerprint;

  const manifestPath = path.posix.join(relativeRoot, "semantic-roles.json");
  await writeFile(
    path.join(cwd, manifestPath),
    JSON.stringify({
      schemaVersion: "1.0",
      kind: "engineering_semantic_roles",
      model: { bundleFingerprint: fingerprint },
      roles: [
        {
          roleId: "TOWER_BASE_LEFT",
          roleType: "TOWER_BASE",
          entity: { type: "NODE", id: 2 },
        },
      ],
    }),
    "utf8",
  );

  const runId = `run_sem${token}`;
  const relativeRunDir = path.posix.join(".femagent", "runs", runId);
  const runDir = path.join(cwd, relativeRunDir);
  await mkdir(runDir, { recursive: true });
  const response = [
    "time_s,relative_displacement_m,relative_velocity_m_s,relative_acceleration_m_s2",
    "0,0,0,0",
    "0.1,0.02,0.2,1",
    "0.2,-0.03,-0.1,-0.5",
    "",
  ].join("\n");
  const summaryObject = {
    responseNode: 2,
    responseDof: 1,
    sampleCount: 3,
    absolutePeakDisplacementM: 0.03,
  };
  const summary = JSON.stringify(summaryObject);
  const solverLog = "semantic bridge test\n";
  await writeFile(path.join(runDir, "response.csv"), response, "utf8");
  await writeFile(path.join(runDir, "result_summary.json"), summary, "utf8");
  await writeFile(path.join(runDir, "solver.log"), solverLog, "utf8");
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
        packageVersion: "3.8.0.0",
        engineVersion: "3.8.0",
        executionMode: "ISOLATED_WORKER_PROCESS",
      },
      model: {
        path: modelPath,
        sha256: "b".repeat(64),
        bundleFingerprint: fingerprint,
      },
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

  return { root, modelPath, manifestPath, runId, fingerprint };
}

test("semantic inspect and resolve cross the strict read-only bridge", async () => {
  const fixture = await createSemanticWorkspace();
  try {
    const inspection = await runFemSemanticInspect(cwd, fixture.modelPath, fixture.manifestPath);
    assert.equal(inspection.status, "RESOLVED");
    assert.equal(inspection.roles[0]?.roleId, "TOWER_BASE_LEFT");

    const resolution = await runFemSemanticResolve(
      cwd,
      fixture.modelPath,
      fixture.manifestPath,
      "TOWER_BASE_LEFT",
    );
    assert.equal(resolution.status, "RESOLVED");
    assert.deepEqual(resolution.entity, { type: "NODE", id: 2 });
    assert.equal(resolution.modelBundleFingerprint, fixture.fingerprint);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
    await rm(path.join(cwd, ".femagent", "runs", fixture.runId), { recursive: true, force: true });
  }
});

test("role evidence bridge retains semantic provenance", async () => {
  const fixture = await createSemanticWorkspace();
  try {
    const report = await runFemRoleEvidenceProject(
      cwd,
      "bridge-demo",
      fixture.modelPath,
      fixture.manifestPath,
      "TOWER_BASE_LEFT",
      fixture.runId,
      "EVID-TS-ROLE-001",
      {
        quantity: "DISPLACEMENT",
        component: "X",
        operation: "SUMMARY",
      },
    );

    const evidence = report.verifiedEvidence[0];
    assert.equal(evidence?.status, "VERIFIED");
    assert.deepEqual(evidence?.metric.target, { type: "NODE", id: 2 });
    const semantic = evidence?.provenance.semanticRole as Record<string, unknown> | undefined;
    assert.equal(semantic?.roleId, "TOWER_BASE_LEFT");
    assert.equal(semantic?.modelBundleFingerprint, fixture.fingerprint);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
    await rm(path.join(cwd, ".femagent", "runs", fixture.runId), { recursive: true, force: true });
  }
});
