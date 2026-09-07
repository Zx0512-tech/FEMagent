import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const TOOL_NAME = "fem_model_spec_validate";

test("ModelSpec validation tool is registered as a dedicated Pi extension", async () => {
  const extensionPath = path.resolve(".pi/extensions/model-spec-tools.ts");
  const extension = await readFile(extensionPath, "utf8");

  assert.match(extension, /name:\s*["']fem_model_spec_validate["']/);
  assert.match(extension, /runFemModelSpecValidate/);
  assert.doesNotMatch(extension, /runFemSolverRun/);
});

test("agent entrypoint loads and allows fem_model_spec_validate", async () => {
  const agent = await readFile(path.resolve("apps/agent/src/main.ts"), "utf8");

  assert.match(agent, /\.pi\/extensions\/model-spec-tools\.ts/);
  assert.ok(agent.includes(`"${TOOL_NAME}"`));
});
