import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import {
  runFemModelInspect,
  runFemResultQuery,
  runFemRoleEvidenceProject,
  runFemSemanticResolve,
} from "@femagent/fem-tools";

const cwd = process.cwd();

function sha256(content: string): string {
  return createHash("sha256").update(content).digest("hex");
}

async function createFixture(): Promise<{
  root: string;
  modelPath: string;
  manifestPath: string;
  runId: string;
}> {
  const token = randomUUID().replaceAll("-", "").slice(0, 12);
  const relativeRoot = path.posix.join(".femagent", "structural-ts-tests", token);
  const root = path.join(cwd, relativeRoot);
  await mkdir(root, { recursive: true });

  const modelPath = path.posix.join(relativeRoot, "model.py");
  await writeFile(
    path.join(cwd, modelPath),
    [
      "import openseespy.opensees as ops",
      "ops.model('basic', '-ndm', 2, '-ndf', 3)",
      "ops.node(1, 0.0, 0.0)",
      "ops.node(2, 1.0, 0.0)",
      "ops.geomTransf('Linear', 1)",
      "ops.element('elasticBeamColumn', 41, 1, 2, 2.0, 30000.0, 100.0, 1)",
      "",
    ].join("\n"),
    "utf8",
  );
  const model = await runFemModelInspect(cwd, modelPath);
  if (model.format !== "OPENSEES_PYTHON") throw new Error("fixture must be OpenSees Python");
  const fingerprint = model.bundle.bundleFingerprint;

  const manifestPath = path.posix.join(relativeRoot, "semantic-roles.json");
  await writeFile(
    path.join(cwd, manifestPath),
    JSON.stringify({
      schemaVersion: "1.0",
      kind: "engineering_semantic_roles",
      model: { bundleFingerprint: fingerprint },
      roles: [
        {
          roleId: "GIRDER_MIDSPAN",
          roleType: "MIDSPAN",
          entity: { type: "ELEMENT", id: 41 },
        },
      ],
    }),
    "utf8",
  );

  const runId = `run_structts${token}`;
  const relativeRunDir = path.posix.join(".femagent", "runs", runId);
  const runDir = path.join(cwd, relativeRunDir);
  await mkdir(runDir, { recursive: true });
  const response = JSON.stringify({
    schemaVersion: "1.0",
    kind: "structural_response_series",
    channels: [
      {
        channelId: "girder_mz_i",
        quantity: "GENERALIZED_FORCE",
        target: { type: "ELEMENT", id: 41 },
        component: "MZ",
        location: "END_I",
        unit: null,
        referenceFrame: "ELEMENT_LOCAL",
        abscissaSemantic: "SOLVER_NATIVE_RESULT_ABSCISSA",
        abscissaUnit: null,
        abscissaValues: [1],
        values: [10],
      },
    ],
  });
  const summary = JSON.stringify({ nodeCount: 2, elementCount: 1 });
  const solverLog = "structural bridge test\n";
  await writeFile(path.join(runDir, "structural_response.json"), response, "utf8");
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
      solver: { name: "OPENSEESPY", executionMode: "ISOLATED_WORKER_PROCESS" },
      model: { path: modelPath, sha256: "b".repeat(64), bundleFingerprint: fingerprint },
      load: { mode: "MODEL_SCRIPT_MANAGED" },
      analysis: { type: "MODEL_SCRIPT" },
      summary: JSON.parse(summary),
      outputs: {
        runManifest: path.posix.join(relativeRunDir, "run_manifest.json"),
        structuralResponse: path.posix.join(relativeRunDir, "structural_response.json"),
        structuralResponseSha256: sha256(response),
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

test("structural ELEMENT result and role evidence cross the read-only bridge", async () => {
  const fixture = await createFixture();
  try {
    const resolution = await runFemSemanticResolve(
      cwd,
      fixture.modelPath,
      fixture.manifestPath,
      "GIRDER_MIDSPAN",
    );
    assert.deepEqual(resolution.entity, { type: "ELEMENT", id: 41 });

    const result = await runFemResultQuery(
      cwd,
      fixture.runId,
      {
        quantity: "GENERALIZED_FORCE",
        target: { type: "ELEMENT", id: 41 },
        component: "MZ",
        location: "END_I",
        operation: "SUMMARY",
      },
    );
    assert.equal(result.location, "END_I");
    assert.deepEqual(result.target, { type: "ELEMENT", id: 41 });
    assert.equal(result.summary?.absolutePeak, 10);

    const evidence = await runFemRoleEvidenceProject(
      cwd,
      "bridge-demo",
      fixture.modelPath,
      fixture.manifestPath,
      "GIRDER_MIDSPAN",
      fixture.runId,
      "EVID-TS-STRUCT-001",
      {
        quantity: "GENERALIZED_FORCE",
        component: "MZ",
        location: "END_I",
        operation: "SUMMARY",
      },
    );
    assert.equal(evidence.verifiedEvidence[0]?.metric.location, "END_I");
    assert.deepEqual(evidence.verifiedEvidence[0]?.metric.target, { type: "ELEMENT", id: 41 });
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
    await rm(path.join(cwd, ".femagent", "runs", fixture.runId), { recursive: true, force: true });
  }
});
