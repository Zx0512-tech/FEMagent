import assert from "node:assert/strict";
import test from "node:test";

import {
  FEM_BRIDGE_PROTOCOL,
  FemBridgeError,
  FemCoreError,
  runFemCoreRequest,
  runFemLoadInspect,
  runFemLoadStandardize,
  runFemModelInspect,
} from "@femagent/fem-tools";

const cwd = process.cwd();

test("model inspection crosses the versioned TypeScript/Python bridge", async () => {
  const report = await runFemModelInspect(cwd, "tests/fixtures/simple_model.apdl");
  assert.equal(report.kind, "model_inspection");
  assert.equal(report.schemaVersion, "1.1");
  assert.equal(report.summary.explicitNodeCommandCount, 2);
  assert.equal(report.validation.executionEligibility, "STATICALLY_ELIGIBLE");
  assert.deepEqual(report.manifest.topology.elementTypes, [{ id: "1", name: "BEAM188" }]);
  assert.equal(report.manifest.topology.nodeCount.value, 2);
});

test("load inspection crosses the versioned TypeScript/Python bridge", async () => {
  const report = await runFemLoadInspect(cwd, "tests/fixtures/earthquake.csv");
  assert.equal(report.kind, "load_inspection");
  assert.equal(report.schemaVersion, "1.1");
  assert.equal(report.rowCount, 4);
  assert.equal(report.columns[0]?.timeCandidate, true);
  assert.equal(report.manifest.time.stepS, 0.02);
  assert.equal(report.suggestedMapping.mapping.component, null);
});

test("load standardization crosses the bridge with explicit confirmed mapping", async () => {
  const report = await runFemLoadStandardize(
    cwd,
    "tests/fixtures/earthquake.csv",
    {
      version: 1,
      loadKind: "EARTHQUAKE",
      timeColumn: "time_s",
      timeUnit: "s",
      valueColumn: "acceleration_g",
      quantity: "ACCELERATION",
      sourceUnit: "g",
      applicationType: "UNIFORM_EXCITATION",
      component: "X",
    },
    ".femagent/test/earthquake.standardized.csv",
  );
  assert.equal(report.kind, "standardized_load");
  assert.equal(report.sampleCount, 4);
  assert.equal(report.channels[0]?.standardUnit, "m/s2");
  assert.match(report.output.sha256, /^[a-f0-9]{64}$/);
});

test("Python domain errors preserve stable error codes", async () => {
  await assert.rejects(
    () => runFemModelInspect(cwd, "tests/fixtures/missing.apdl"),
    (error: unknown) => error instanceof FemCoreError && error.code === "FILE_NOT_FOUND",
  );
});

test("bridge request exposes protocol version and enforces timeout", async () => {
  assert.equal(FEM_BRIDGE_PROTOCOL, "femagent.bridge/v1");
  await assert.rejects(
    () => runFemCoreRequest(cwd, "health", {}, { timeoutMs: 1 }),
    (error: unknown) => error instanceof FemBridgeError && error.code === "BRIDGE_TIMEOUT",
  );
});
