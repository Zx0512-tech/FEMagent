import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import {
  runFemAnalysisReadiness,
  runFemAnalysisRenderOpenSees,
  runFemModelSpecValidate,
  type FemAnalysisReadiness,
  type FemEngineeringAnalysisSpecV1Input,
  type FemEngineeringLinearStaticAnalysisSpecV2Input,
  type FemEngineeringModelSpecInput,
  type FemOpenSeesAnalysisRenderResult,
} from "@femagent/fem-tools";

async function loadModel(): Promise<FemEngineeringModelSpecInput> {
  const fixture = path.resolve("tests/fixtures/model_spec/simple-portal-frame.json");
  return JSON.parse(await readFile(fixture, "utf8")) as FemEngineeringModelSpecInput;
}

async function fingerprint(model: FemEngineeringModelSpecInput): Promise<string> {
  const validation = await runFemModelSpecValidate(process.cwd(), model);
  assert.equal(validation.status, "VALID");
  assert.ok(validation.modelSpecFingerprint);
  return validation.modelSpecFingerprint;
}

async function boundAnalysis(model: FemEngineeringModelSpecInput): Promise<FemEngineeringAnalysisSpecV1Input> {
  return {
    schemaVersion: "1.0",
    kind: "engineering_analysis_spec",
    modelSpecFingerprint: await fingerprint(model),
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

async function boundV2Static(
  model: FemEngineeringModelSpecInput,
): Promise<FemEngineeringLinearStaticAnalysisSpecV2Input> {
  return {
    schemaVersion: "2.0",
    kind: "engineering_analysis_spec",
    modelSpecFingerprint: await fingerprint(model),
    analysisType: "LINEAR_STATIC",
    units: { force: "N" },
    definition: {
      loadCases: [
        {
          loadCaseId: "LC1",
          nodalLoads: [{ nodeId: 3, FX: 0, FY: -10000, MZ: 0 }],
        },
      ],
    },
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

test("V1 Analysis Readiness crosses the strict TypeScript/Python bridge", async () => {
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

test("V1 OpenSees analysis rendering crosses the strict TypeScript/Python bridge", async () => {
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

test("V2 static Analysis Readiness crosses the widened TypeScript/Python bridge", async () => {
  const model = await loadModel();
  const analysis = await boundV2Static(model);
  const report: FemAnalysisReadiness = await runFemAnalysisReadiness(
    process.cwd(),
    model,
    analysis,
  );

  assert.equal(report.schema, "FEMAGENT_ANALYSIS_READINESS_V2");
  assert.equal(report.status, "READY");
  assert.equal(report.profile, "OPENSEES_FRAME_2D_LINEAR_STATIC_V2");
  assert.equal(report.checks.responseMapping.status, "PASS");
});

test("V2 static OpenSees rendering returns the V2 discriminated contract", async () => {
  const model = await loadModel();
  const analysis = await boundV2Static(model);
  const report: FemOpenSeesAnalysisRenderResult = await runFemAnalysisRenderOpenSees(
    process.cwd(),
    model,
    analysis,
  );

  assert.equal(report.schema, "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V2");
  assert.equal(report.status, "RENDERED");
  if (report.schema === "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V2" && report.status === "RENDERED") {
    assert.equal(report.renderer.name, "OPENSEES_FRAME_2D_LINEAR_STATIC_V2");
    assert.equal(report.renderer.version, "2.0");
    assert.match(report.analysisRenderFingerprint, /^[0-9a-f]{64}$/);
  }
});
