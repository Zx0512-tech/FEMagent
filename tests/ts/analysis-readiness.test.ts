import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import {
  runFemAnalysisReadiness,
  runFemAnalysisRenderOpenSees,
  runFemModelSpecValidate,
  type FemAnalysisReadiness,
  type FemEngineeringAnalysisSpecInput,
  type FemEngineeringModelSpecInput,
  type FemOpenSeesAnalysisRenderResult,
} from "@femagent/fem-tools";

async function loadModel(): Promise<FemEngineeringModelSpecInput> {
  const fixture = path.resolve("tests/fixtures/model_spec/simple-portal-frame.json");
  return JSON.parse(await readFile(fixture, "utf8")) as FemEngineeringModelSpecInput;
}

async function boundAnalysis(model: FemEngineeringModelSpecInput): Promise<FemEngineeringAnalysisSpecInput> {
  const validation = await runFemModelSpecValidate(process.cwd(), model);
  assert.equal(validation.status, "VALID");
  assert.ok(validation.modelSpecFingerprint);
  return {
    schemaVersion: "1.0",
    kind: "engineering_analysis_spec",
    modelSpecFingerprint: validation.modelSpecFingerprint,
    analysisType: "LINEAR_STATIC",
    units: { force: "N" },
    loadCases: [
      {
        loadCaseId: "LC1",
        nodalLoads: [{ nodeId: 3, FX: 0, FY: -10000, MZ: 0 }],
      },
    ],
    resultRequests: [
      {
        requestId: "R1",
        loadCaseId: "LC1",
        quantity: "DISPLACEMENT",
        target: { type: "NODE", id: 3 },
        component: "Y",
      },
    ],
  };
}

test("Analysis Readiness crosses the strict TypeScript/Python bridge", async () => {
  const model = await loadModel();
  const analysis = await boundAnalysis(model);
  const report: FemAnalysisReadiness = await runFemAnalysisReadiness(
    process.cwd(),
    model,
    analysis,
  );

  assert.equal(report.schema, "FEMAGENT_ANALYSIS_READINESS_V1");
  assert.equal(report.status, "READY");
  assert.equal(report.profile, "OPENSEES_FRAME_2D_LINEAR_STATIC_V1");
  assert.equal(report.checks.responseMapping.status, "PASS");
});

test("OpenSees analysis rendering crosses the strict TypeScript/Python bridge", async () => {
  const model = await loadModel();
  const analysis = await boundAnalysis(model);
  const report: FemOpenSeesAnalysisRenderResult = await runFemAnalysisRenderOpenSees(
    process.cwd(),
    model,
    analysis,
  );

  assert.equal(report.schema, "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V1");
  assert.equal(report.status, "RENDERED");
  if (report.status === "RENDERED") {
    assert.match(report.analysisRenderFingerprint, /^[0-9a-f]{64}$/);
    assert.ok(report.artifacts.analysisPath.endsWith("analysis.py"));
    assert.ok(report.artifacts.responsePlanPath.endsWith("response_plan.json"));
    assert.ok(report.artifacts.readinessPath.endsWith("analysis_readiness.json"));
    assert.ok(report.artifacts.manifestPath.endsWith("analysis_manifest.json"));
  }
});
