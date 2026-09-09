import assert from "node:assert/strict";
import test from "node:test";

import {
  runFemAnalysisSpecMigrateV1ToV2,
  runFemAnalysisSpecValidate,
  type FemEngineeringAnalysisSpecV1Input,
  type FemEngineeringLinearStaticAnalysisSpecV2Input,
  type FemEngineeringModalAnalysisSpecV2Input,
  type FemEngineeringTransientAnalysisSpecV2Input,
} from "@femagent/fem-tools";

const MODEL_FP = "0".repeat(64);
const LOAD_SHA = "a".repeat(64);

const v1Static: FemEngineeringAnalysisSpecV1Input = {
  schemaVersion: "1.0",
  kind: "engineering_analysis_spec",
  modelSpecFingerprint: MODEL_FP,
  analysisType: "LINEAR_STATIC",
  units: { force: "N" },
  loadCases: [
    {
      loadCaseId: "LC1",
      nodalLoads: [{ nodeId: 2, FX: 0, FY: -10, MZ: 0 }],
    },
  ],
  resultRequests: [
    {
      requestId: "R1",
      loadCaseId: "LC1",
      quantity: "DISPLACEMENT",
      target: { type: "NODE", id: 2 },
      component: "Y",
    },
  ],
};

const v2Static: FemEngineeringLinearStaticAnalysisSpecV2Input = {
  schemaVersion: "2.0",
  kind: "engineering_analysis_spec",
  modelSpecFingerprint: MODEL_FP,
  analysisType: "LINEAR_STATIC",
  units: { force: "N" },
  definition: {
    loadCases: [
      {
        loadCaseId: "LC1",
        nodalLoads: [{ nodeId: 2, FX: 0, FY: -10, MZ: 0 }],
      },
    ],
  },
  resultRequests: [
    {
      requestId: "R1",
      loadCaseId: "LC1",
      quantity: "DISPLACEMENT",
      target: { type: "NODE", id: 2 },
      component: "Y",
    },
  ],
};

const modal: FemEngineeringModalAnalysisSpecV2Input = {
  schemaVersion: "2.0",
  kind: "engineering_analysis_spec",
  modelSpecFingerprint: MODEL_FP,
  analysisType: "MODAL",
  units: {},
  definition: { modeCount: 3 },
  resultRequests: [
    { requestId: "FREQ1", quantity: "NATURAL_FREQUENCY", mode: 1 },
    {
      requestId: "MODE1Y",
      quantity: "MODE_SHAPE",
      mode: 1,
      target: { type: "NODE", id: 3 },
      component: "Y",
    },
  ],
};

const nodalTransient: FemEngineeringTransientAnalysisSpecV2Input = {
  schemaVersion: "2.0",
  kind: "engineering_analysis_spec",
  modelSpecFingerprint: MODEL_FP,
  analysisType: "TRANSIENT",
  units: { force: "N" },
  definition: {
    time: { timeStep: 0.01, duration: 1 },
    damping: { type: "NONE" },
    excitation: {
      type: "NODAL_TIME_HISTORY",
      nodeId: 3,
      component: "Y",
      quantity: "FORCE",
      loadArtifact: { path: "loads/force.csv", sha256: LOAD_SHA },
    },
  },
  resultRequests: [
    {
      requestId: "A3Y",
      quantity: "ACCELERATION",
      target: { type: "NODE", id: 3 },
      component: "Y",
    },
  ],
};

const baseTransient: FemEngineeringTransientAnalysisSpecV2Input = {
  schemaVersion: "2.0",
  kind: "engineering_analysis_spec",
  modelSpecFingerprint: MODEL_FP,
  analysisType: "TRANSIENT",
  units: {},
  definition: {
    time: { timeStep: 0.01, duration: 1 },
    damping: { type: "RAYLEIGH", alphaM: 0, betaK: 0.002 },
    excitation: {
      type: "UNIFORM_BASE_EXCITATION",
      component: "X",
      quantity: "ACCELERATION",
      loadArtifact: { path: "loads/eq.csv", sha256: LOAD_SHA },
    },
  },
  resultRequests: [
    {
      requestId: "A3X",
      quantity: "ABSOLUTE_ACCELERATION",
      target: { type: "NODE", id: 3 },
      component: "X",
    },
  ],
};

test("typed AnalysisSpec V2 profiles cross intrinsic validation", async () => {
  for (const spec of [v2Static, modal, nodalTransient, baseTransient]) {
    const report = await runFemAnalysisSpecValidate(process.cwd(), spec);
    assert.equal(report.status, "VALID");
    assert.equal(report.normalizedSpec?.schemaVersion, "2.0");
  }
});

test("typed V1 static migration crosses the bridge", async () => {
  const report = await runFemAnalysisSpecMigrateV1ToV2(process.cwd(), v1Static);
  assert.equal(report.status, "MIGRATED");
  assert.equal(report.candidateSpec?.schemaVersion, "2.0");
  assert.equal(report.candidateSpec?.analysisType, "LINEAR_STATIC");
});
