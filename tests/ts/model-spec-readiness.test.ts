import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  runFemModelSpecReadiness,
  type FemEngineeringModelSpecInput,
  type FemModelSpecReadiness,
} from "@femagent/fem-tools";

async function loadSpec(): Promise<FemEngineeringModelSpecInput> {
  return JSON.parse(
    await readFile("tests/fixtures/model_spec/simple-portal-frame.json", "utf8"),
  ) as FemEngineeringModelSpecInput;
}

test("ModelSpec readiness crosses the strict TypeScript/Python bridge", async () => {
  const result: FemModelSpecReadiness = await runFemModelSpecReadiness(
    process.cwd(),
    await loadSpec(),
  );

  assert.equal(result.schema, "FEMAGENT_MODEL_SPEC_READINESS_V1");
  assert.equal(result.status, "READY");
  assert.equal(result.profile, "FRAME_2D_ELASTIC_READINESS_V1");
  assert.equal(result.checks.connectivity.componentCount, 1);
  assert.equal(result.checks.rigidBodyRestraint.components[0]?.constraintRank, 3);
});

test("invalid ModelSpec content remains a typed readiness result", async () => {
  const invalid = JSON.parse(
    await readFile("tests/fixtures/model_spec/simple-portal-frame.json", "utf8"),
  ) as Record<string, unknown>;
  delete invalid.units;

  const result = await runFemModelSpecReadiness(
    process.cwd(),
    invalid as unknown as FemEngineeringModelSpecInput,
  );

  assert.equal(result.status, "INVALID_SPEC");
  assert.equal(result.checks.connectivity.status, "SKIPPED");
  assert.equal(result.modelSpecFingerprint, null);
});
