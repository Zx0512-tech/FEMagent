import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const TOOL_NAME = "fem_analysis_spec_validate";

test("AnalysisSpec validation is registered as a dedicated SAFE read-only Pi tool", async () => {
  const extensionPath = path.resolve(".pi/extensions/analysis-spec-tools.ts");
  const extension = await readFile(extensionPath, "utf8");

  assert.match(extension, /name:\s*["']fem_analysis_spec_validate["']/);
  assert.match(extension, /runFemAnalysisSpecValidate/);
  assert.match(extension, /SAFE|read-only/i);
  assert.doesNotMatch(extension, /runFemSolverRun/);
  assert.doesNotMatch(extension, /runFemSolverPreflight/);
  assert.doesNotMatch(extension, /outputPath/);
  assert.doesNotMatch(extension, /renderOpenSees|runFemModelSpecRenderOpenSees/);
});

test("agent entrypoint loads and allows AnalysisSpec validation", async () => {
  const agent = await readFile(path.resolve("apps/agent/src/main.ts"), "utf8");

  assert.match(agent, /\.pi\/extensions\/analysis-spec-tools\.ts/);
  assert.ok(agent.includes(`"${TOOL_NAME}"`));
});
