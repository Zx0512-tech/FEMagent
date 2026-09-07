import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const TOOL_NAME = "fem_requirement_complete";

test("requirement completion is a dedicated SAFE Pi tool", async () => {
  const extension = await readFile(
    path.resolve(".pi/extensions/requirement-tools.ts"),
    "utf8",
  );

  assert.match(extension, /name:\s*["']fem_requirement_complete["']/);
  assert.match(extension, /runFemRequirementComplete/);
  assert.match(extension, /SAFE|read-only/i);
  assert.doesNotMatch(extension, /runFemSolverRun/);
  assert.doesNotMatch(extension, /runFemModelSpecRenderOpenSees/);
  assert.doesNotMatch(extension, /outputPath/);
  assert.match(extension, /USER_EXPLICIT/);
  assert.match(extension, /COMPLETE/);
  assert.match(extension, /READY/);
});

test("agent loads and allows requirement completion before ModelSpec tools", async () => {
  const agent = await readFile(path.resolve("apps/agent/src/main.ts"), "utf8");

  assert.match(agent, /\.pi\/extensions\/requirement-tools\.ts/);
  assert.ok(agent.includes(`"${TOOL_NAME}"`));
  assert.ok(
    agent.indexOf(`"${TOOL_NAME}"`) < agent.indexOf('"fem_model_spec_validate"'),
    "requirement completion should appear before ModelSpec validation in the agent workflow",
  );
});
