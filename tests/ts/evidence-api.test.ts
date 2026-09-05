import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { runFemEvidenceProject } from "@femagent/fem-tools";

const cwd = process.cwd();

function sha256(content: string): string {
  return createHash("sha256").update(content).digest("hex");
}

async function writeEvidenceRun(): Promise<{ runId: string; runDir: string }> {
  const runId = `run_ev${randomUUID().replaceAll("-", "").slice(0, 12)}`;
  const relativeRunDir = path.posix.join(".femagent", "runs", runId);
  const runDir = path.join(cwd, relativeRunDir);
  await mkdir(runDir, { recursive: true });

  const response = [
    "time_s,relative_displacement_m,relative_velocity_m_s,relative_acceleration_m_s2",
    "0,0,0,0",
    "0.1,0.02,0.2,1",
    "0.2,-0.03,-0.1,-0.5",
    "0.3,0.01,0,0.25",
    "",
  ].join("\n");
  const summaryObject = {
    responseNode: 2,
    responseDof: 1,
    sampleCount: 4,
    absolutePeakDisplacementM: 0.03,
  };
  const summary = JSON.stringify(summaryObject);
  const solverLog = "evidence bridge test\n";
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
      model: { path: "model.json", sha256: "b".repeat(64) },
      load: { path: "load.csv", sha256: "c".repeat(64) },
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
  return { runId, runDir };
}

test("Engineering Evidence projection crosses the strict read-only bridge", async () => {
  const { runId, runDir } = await writeEvidenceRun();
  try {
    const report = await runFemEvidenceProject(
      cwd,
      "bridge-demo",
      runId,
      "EVID-TS-001",
      {
        quantity: "DISPLACEMENT",
        target: { type: "NODE", id: 2 },
        component: "UX",
        operation: "SUMMARY",
      },
    );

    assert.equal(report.projectId, "bridge-demo");
    assert.equal(report.solverRuns[0]?.runId, runId);
    assert.equal(report.verifiedEvidence.length, 1);
    assert.equal(report.verifiedEvidence[0]?.status, "VERIFIED");
    assert.equal(report.verifiedEvidence[0]?.metric.summary?.absolutePeak, 0.03);
    assert.deepEqual(report.limitations, []);
  } finally {
    await rm(runDir, { recursive: true, force: true });
  }
});
