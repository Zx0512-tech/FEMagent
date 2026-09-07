import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const VALIDATE_TOOL_NAME = "fem_model_spec_validate";
const READINESS_TOOL_NAME = "fem_model_spec_readiness";

test("ModelSpec validation and readiness tools are registered in the dedicated Pi extension", async () => {
  const extensionPath = path.resolve(".pi/extensions/model-spec-tools.ts");
  const extension = await readFile(extensionPath, "utf8");

  assert.match(extension, /name:\s*["']fem_model_spec_validate["']/);
  assert.match(extension, /runFemModelSpecValidate/);
  assert.match(extension, /name:\s*["']fem_model_spec_readiness["']/);
  assert.match(extension, /runFemModelSpecReadiness/);
  assert.doesNotMatch(extension, /runFemSolverRun/);
});

test("agent entrypoint loads and allows ModelSpec validation and readiness tools", async () => {
  const agent = await readFile(path.resolve("apps/agent/src/main.ts"), "utf8");

  assert.match(agent, /\.pi\/extensions\/model-spec-tools\.ts/);
  assert.ok(agent.includes(`"${VALIDATE_TOOL_NAME}"`));
  assert.ok(agent.includes(`"${READINESS_TOOL_NAME}"`));
});
