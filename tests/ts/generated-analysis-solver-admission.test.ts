import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import {
  runFemAnalysisRenderOpenSees,
  runFemModelSpecValidate,
  runFemSolverPreflight,
  type FemEngineeringAnalysisSpecV1Input,
  type FemEngineeringModelSpecInput,
  type FemSolverOptions,
} from "@femagent/fem-tools";

async function loadModel(): Promise<FemEngineeringModelSpecInput> {
  const fixture = path.resolve("tests/fixtures/model_spec/simple-portal-frame.json");
  return JSON.parse(await readFile(fixture, "utf8")) as FemEngineeringModelSpecInput;
}

async function boundAnalysis(model: FemEngineeringModelSpecInput): Promise<FemEngineeringAnalysisSpecV1Input> {
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

test("generated OpenSees analysis admission is represented by the typed solver option contract", async () => {
  const model = await loadModel();
  const analysis = await boundAnalysis(model);
  const rendered = await runFemAnalysisRenderOpenSees(process.cwd(), model, analysis);
  assert.equal(rendered.status, "RENDERED");
  if (rendered.status !== "RENDERED") throw new Error("expected rendered analysis bundle");

  const solverOptions: FemSolverOptions = {
    responsePlanPath: rendered.artifacts.responsePlanPath,
    analysisManifestPath: rendered.artifacts.manifestPath,
  };

  const preflight = await runFemSolverPreflight(
    process.cwd(),
    "opensees",
    rendered.artifacts.analysisPath,
    undefined,
    solverOptions,
  );
  assert.equal(preflight.status, "READY");
  assert.ok(preflight.checks.some((check) => check.code === "GENERATED_ANALYSIS_VERIFIED" && check.status === "PASSED"));
});

test("V2 generated OpenSees admission uses the same typed solver options without execution mode", async () => {
  const model = await loadModel();
  const v1 = await boundAnalysis(model);
  const analysis: FemEngineeringLinearStaticAnalysisSpecV2Input = {
    schemaVersion: "2.0",
    kind: "engineering_analysis_spec",
    modelSpecFingerprint: v1.modelSpecFingerprint,
    analysisType: "LINEAR_STATIC",
    units: v1.units,
    definition: { loadCases: v1.loadCases },
    resultRequests: v1.resultRequests,
  };
  const rendered = await runFemAnalysisRenderOpenSees(process.cwd(), model, analysis);
  assert.equal(rendered.schema, "FEMAGENT_OPENSEES_ANALYSIS_RENDER_V2");
  assert.equal(rendered.status, "RENDERED");
  if (rendered.status !== "RENDERED") throw new Error("expected rendered V2 analysis bundle");

  const solverOptions: FemSolverOptions = {
    responsePlanPath: rendered.artifacts.responsePlanPath,
    analysisManifestPath: rendered.artifacts.manifestPath,
  };
  assert.deepEqual(Object.keys(solverOptions).sort(), ["analysisManifestPath", "responsePlanPath"]);

  const preflight = await runFemSolverPreflight(
    process.cwd(),
    "opensees",
    rendered.artifacts.analysisPath,
    undefined,
    solverOptions,
  );
  assert.equal(preflight.status, "READY");
  assert.ok(preflight.checks.some((check) => check.code === "GENERATED_ANALYSIS_VERIFIED" && check.status === "PASSED"));
});

test("solver tool guidance preserves generated-analysis manifest and execution boundaries", async () => {
  const source = await readFile(path.resolve(".pi/extensions/fem-tools.ts"), "utf8");

  assert.match(source, /analysisManifestPath/);
  assert.match(source, /generated[- ]analysis/i);
  assert.match(source, /same.*responsePlanPath.*analysisManifestPath|same.*analysisManifestPath.*responsePlanPath/i);
  assert.match(source, /external load|loadPath/i);
  assert.match(source, /fail[- ]closed|must not/i);
});
