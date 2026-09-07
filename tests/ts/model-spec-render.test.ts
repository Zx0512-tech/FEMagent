import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  runFemModelSpecRenderOpenSees,
  type FemEngineeringModelSpecInput,
  type FemOpenSeesRenderResult,
} from "@femagent/fem-tools";

const fixturePath = join(process.cwd(), "tests/fixtures/model_spec/simple-portal-frame.json");

async function loadSpec(): Promise<FemEngineeringModelSpecInput> {
  return JSON.parse(await readFile(fixturePath, "utf8")) as FemEngineeringModelSpecInput;
}

async function makeWorkspace(): Promise<string> {
  const workspace = await mkdtemp(join(tmpdir(), "femagent-render-ts-"));
  await writeFile(join(workspace, "placeholder.txt"), "workspace", "utf8");
  return workspace;
}

test("OpenSees ModelSpec rendering crosses the strict TypeScript/Python bridge", async () => {
  const workspace = await makeWorkspace();
  const spec = await loadSpec();

  const report: FemOpenSeesRenderResult = await runFemModelSpecRenderOpenSees(workspace, spec);

  assert.equal(report.schema, "FEMAGENT_OPENSEES_RENDER_V1");
  assert.equal(report.status, "RENDERED");
  if (report.status !== "RENDERED") throw new Error("expected rendered result");
  assert.equal(report.renderer.name, "OPENSEES_FRAME_2D_V1");
  assert.equal(report.renderer.version, "1.0");
  assert.match(report.artifacts.modelPath, /^\.femagent\/generated-models\/render_[0-9a-f]{16}\/model\.py$/);
  assert.match(report.artifacts.modelSha256, /^[0-9a-f]{64}$/);
  assert.match(report.renderFingerprint, /^[0-9a-f]{64}$/);
});

test("NOT_READY ModelSpec remains a typed BLOCKED render result", async () => {
  const workspace = await makeWorkspace();
  const spec = await loadSpec();
  spec.constraints = [];

  const report = await runFemModelSpecRenderOpenSees(workspace, spec);

  assert.equal(report.status, "BLOCKED");
  if (report.status !== "BLOCKED") throw new Error("expected blocked result");
  assert.equal(report.reason, "MODEL_NOT_READY");
  assert.equal(report.readiness.status, "NOT_READY");
  assert.equal(report.artifacts, null);
  assert.equal(report.renderFingerprint, null);
});
