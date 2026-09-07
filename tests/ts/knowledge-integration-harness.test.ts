import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { runFemEvidenceProject } from "@femagent/fem-tools";
import {
  KnowledgeError,
  composeUnifiedEvidenceBundle,
  createConfiguredKnowledgeProvider,
  knowledgeEvidenceFromSearchResult,
} from "@femagent/knowledge-client";

const cwd = process.cwd();
const fixturePath = "tests/fixtures/knowledge/seismic-time-history.json";

function sha256(content: string): string {
  return createHash("sha256").update(content).digest("hex");
}

async function writeEvidenceRun(): Promise<{ runId: string; runDir: string }> {
  const runId = `run_kh${randomUUID().replaceAll("-", "").slice(0, 12)}`;
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
  const solverLog = "knowledge integration harness evidence run\n";

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

async function projectEngineeringEvidence(runId: string) {
  return await runFemEvidenceProject(
    cwd,
    "knowledge-harness",
    runId,
    "EVID-KNOW-001",
    {
      quantity: "DISPLACEMENT",
      target: { type: "NODE", id: 2 },
      component: "UX",
      operation: "SUMMARY",
    },
  );
}

test("unified evidence keeps fixture knowledge separate from verified FEM numerical truth", async () => {
  const { runId, runDir } = await writeEvidenceRun();
  try {
    const engineeringReport = await projectEngineeringEvidence(runId);
    assert.equal(engineeringReport.verifiedEvidence[0]?.status, "VERIFIED");
    assert.equal(engineeringReport.verifiedEvidence[0]?.metric.summary?.absolutePeak, 0.03);
    const engineeringSnapshot = structuredClone(engineeringReport.verifiedEvidence[0]);

    const provider = await createConfiguredKnowledgeProvider(cwd, {
      ENGIKNOW_KNOWLEDGE_MODE: "fixture",
      ENGIKNOW_KNOWLEDGE_FIXTURE: fixturePath,
    });
    const search = await provider.search({ query: "seismic time history", topK: 1 });
    const knowledgeEvidence = knowledgeEvidenceFromSearchResult(search);
    assert.match(knowledgeEvidence[0]?.claim ?? "", /9999/);

    const bundle = composeUnifiedEvidenceBundle({
      projectId: "knowledge-harness",
      knowledgeEvidence,
      engineeringReport,
    });

    assert.equal(bundle.schema, "FEMAGENT_UNIFIED_EVIDENCE_V1");
    assert.equal(bundle.projectId, "knowledge-harness");
    assert.equal(bundle.knowledgeEvidence.length, 1);
    assert.equal(bundle.knowledgeEvidence[0]?.status, "RETRIEVED");
    assert.equal(bundle.engineeringEvidence.length, 1);
    assert.equal(bundle.engineeringEvidence[0], engineeringReport.verifiedEvidence[0]);
    assert.deepEqual(bundle.engineeringEvidence[0], engineeringSnapshot);
    assert.equal(bundle.engineeringEvidence[0]?.status, "VERIFIED");
    assert.equal(bundle.engineeringEvidence[0]?.metric.summary?.absolutePeak, 0.03);
  } finally {
    await rm(runDir, { recursive: true, force: true });
  }
});

test("invalid fixture retrieval cannot mutate an already verified Engineering Evidence report", async () => {
  const { runId, runDir } = await writeEvidenceRun();
  const tempDir = path.join(cwd, ".femagent", "test-knowledge-harness");
  const relativeFixture = path.posix.join(".femagent", "test-knowledge-harness", "invalid.json");
  await mkdir(tempDir, { recursive: true });
  try {
    const engineeringReport = await projectEngineeringEvidence(runId);
    const reportSnapshot = structuredClone(engineeringReport);
    await writeFile(path.join(tempDir, "invalid.json"), "{bad", "utf8");

    const provider = await createConfiguredKnowledgeProvider(cwd, {
      ENGIKNOW_KNOWLEDGE_MODE: "fixture",
      ENGIKNOW_KNOWLEDGE_FIXTURE: relativeFixture,
    });
    await assert.rejects(
      () => provider.search({ query: "seismic time history" }),
      (error: unknown) => error instanceof KnowledgeError && error.code === "INVALID_KNOWLEDGE_FIXTURE",
    );

    assert.deepEqual(engineeringReport, reportSnapshot);
    assert.equal(engineeringReport.verifiedEvidence[0]?.metric.summary?.absolutePeak, 0.03);
  } finally {
    await rm(runDir, { recursive: true, force: true });
    await rm(tempDir, { recursive: true, force: true });
  }
});
