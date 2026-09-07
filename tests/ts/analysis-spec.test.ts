import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import {
  runFemAnalysisSpecValidate,
  type FemEngineeringAnalysisSpecInput,
} from "@femagent/fem-tools";

async function loadSpec(): Promise<FemEngineeringAnalysisSpecInput> {
  const fixture = path.resolve("tests/fixtures/analysis_spec/simple-linear-static.json");
  return JSON.parse(await readFile(fixture, "utf8")) as FemEngineeringAnalysisSpecInput;
}

test("AnalysisSpec validation crosses the strict TypeScript/Python bridge", async () => {
  const report = await runFemAnalysisSpecValidate(process.cwd(), await loadSpec());

  assert.equal(report.schema, "FEMAGENT_ANALYSIS_SPEC_VALIDATION_V1");
  assert.equal(report.status, "VALID");
  assert.equal(report.issues.length, 0);
  assert.ok(report.normalizedSpec);
  assert.match(report.analysisSpecFingerprint ?? "", /^[0-9a-f]{64}$/);
});

test("invalid AnalysisSpec content remains a typed validation result", async () => {
  const spec = await loadSpec();
  const invalid = {
    ...spec,
    analysisType: "MODAL",
  } as unknown as FemEngineeringAnalysisSpecInput;

  const report = await runFemAnalysisSpecValidate(process.cwd(), invalid);

  assert.equal(report.status, "INVALID");
  assert.equal(report.normalizedSpec, null);
  assert.equal(report.analysisSpecFingerprint, null);
  assert.ok(
    report.issues.some(
      (issue) => issue.code === "ANALYSIS_SPEC_UNSUPPORTED_ANALYSIS_TYPE",
    ),
  );
});
