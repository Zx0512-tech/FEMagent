import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const TOOL_NAME = "fem_analysis_spec_validate";

test("AnalysisSpec validation exposes V1 plus all V2 intrinsic profiles", async () => {
  const extensionPath = path.resolve(".pi/extensions/analysis-spec-tools.ts");
  const extension = await readFile(extensionPath, "utf8");

  assert.match(extension, /name:\s*["']fem_analysis_spec_validate["']/);
  assert.match(extension, /runFemAnalysisSpecValidate/);
  assert.match(extension, /Type\.Literal\("2\.0"\)/);
  assert.match(extension, /Type\.Literal\("MODAL"\)/);
  assert.match(extension, /Type\.Literal\("TRANSIENT"\)/);
  assert.match(extension, /NODAL_TIME_HISTORY/);
  assert.match(extension, /UNIFORM_BASE_EXCITATION/);
  assert.match(extension, /VALID.*V2.*intrinsic/is);
  assert.match(extension, /V2.*not.*READY|V2.*does not.*establish.*READY/is);
  assert.match(extension, /SAFE|read-only/i);
  assert.match(extension, /temporary|tool surface|high-level/i);
  assert.doesNotMatch(extension, /name:\s*["']fem_analysis_spec_migrate/i);
  assert.doesNotMatch(extension, /runFemAnalysisSpecMigrateV1ToV2/);
  assert.doesNotMatch(extension, /runFemSolverRun/);
  assert.doesNotMatch(extension, /runFemSolverPreflight/);
  assert.doesNotMatch(extension, /outputPath/);
  assert.doesNotMatch(extension, /runFemModelSpecRenderOpenSees/);
});

test("agent entrypoint loads and allows AnalysisSpec validation", async () => {
  const agent = await readFile(path.resolve("apps/agent/src/main.ts"), "utf8");

  assert.match(agent, /\.pi\/extensions\/analysis-spec-tools\.ts/);
  assert.ok(agent.includes(`"${TOOL_NAME}"`));
  assert.doesNotMatch(agent, /fem_analysis_spec_migrate/i);
});
