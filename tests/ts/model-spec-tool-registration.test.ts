import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const VALIDATE_TOOL_NAME = "fem_model_spec_validate";
const READINESS_TOOL_NAME = "fem_model_spec_readiness";
const RENDER_TOOL_NAME = "fem_model_render_opensees";

test("ModelSpec validation readiness and renderer tools are registered in the dedicated Pi extension", async () => {
  const extensionPath = path.resolve(".pi/extensions/model-spec-tools.ts");
  const extension = await readFile(extensionPath, "utf8");

  assert.match(extension, /name:\s*["']fem_model_spec_validate["']/);
  assert.match(extension, /runFemModelSpecValidate/);
  assert.match(extension, /name:\s*["']fem_model_spec_readiness["']/);
  assert.match(extension, /runFemModelSpecReadiness/);
  assert.match(extension, /name:\s*["']fem_model_render_opensees["']/);
  assert.match(extension, /runFemModelSpecRenderOpenSees/);
  assert.doesNotMatch(extension, /runFemSolverRun/);
  assert.doesNotMatch(extension, /outputPath/);
});

test("agent entrypoint loads and allows ModelSpec validation readiness and renderer tools", async () => {
  const agent = await readFile(path.resolve("apps/agent/src/main.ts"), "utf8");

  assert.match(agent, /\.pi\/extensions\/model-spec-tools\.ts/);
  assert.ok(agent.includes(`"${VALIDATE_TOOL_NAME}"`));
  assert.ok(agent.includes(`"${READINESS_TOOL_NAME}"`));
  assert.ok(agent.includes(`"${RENDER_TOOL_NAME}"`));
});
