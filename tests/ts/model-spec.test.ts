import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import {
  runFemModelSpecValidate,
  type FemEngineeringModelSpecInput,
} from "@femagent/fem-tools";

async function loadSpec(): Promise<FemEngineeringModelSpecInput> {
  const fixture = path.resolve("tests/fixtures/model_spec/simple-portal-frame.json");
  return JSON.parse(await readFile(fixture, "utf8")) as FemEngineeringModelSpecInput;
}

test("ModelSpec validation crosses the strict TypeScript/Python bridge", async () => {
  const report = await runFemModelSpecValidate(process.cwd(), await loadSpec());

  assert.equal(report.schema, "FEMAGENT_MODEL_SPEC_VALIDATION_V1");
  assert.equal(report.status, "VALID");
  assert.equal(report.issues.length, 0);
  assert.ok(report.normalizedSpec);
  assert.match(report.modelSpecFingerprint ?? "", /^[0-9a-f]{64}$/);
});

test("invalid ModelSpec content remains a typed validation result", async () => {
  const spec = await loadSpec();
  const invalid: FemEngineeringModelSpecInput = {
    ...spec,
    elements: spec.elements.map((element, index) =>
      index === 0 ? { ...element, nodeJ: 99 } : element,
    ),
  };

  const report = await runFemModelSpecValidate(process.cwd(), invalid);

  assert.equal(report.status, "INVALID");
  assert.equal(report.normalizedSpec, null);
  assert.equal(report.modelSpecFingerprint, null);
  assert.ok(report.issues.some((issue) => issue.code === "MODEL_SPEC_ELEMENT_NODE_NOT_FOUND"));
});
