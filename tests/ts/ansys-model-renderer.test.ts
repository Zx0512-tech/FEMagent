import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  runFemModelSpecRenderAnsys,
  type FemEngineeringModelSpecInput,
} from "@femagent/fem-tools";

async function modelSpec(): Promise<FemEngineeringModelSpecInput> {
  const model = JSON.parse(
    await readFile("tests/fixtures/model_spec/simple-portal-frame.json", "utf8"),
  ) as FemEngineeringModelSpecInput;
  model.nodalMasses = [{ nodeId: 3, mUX: 100, mUY: 80 }];
  return model;
}

test("PR33 TypeScript bridge renders deterministic ANSYS ModelSpec bundle", async () => {
  const rendered = await runFemModelSpecRenderAnsys(
    process.cwd(),
    await modelSpec(),
  );

  assert.equal(rendered.status, "RENDERED");
  if (rendered.status !== "RENDERED") return;
  assert.equal(rendered.schema, "FEMAGENT_ANSYS_MODEL_RENDER_V1");
  assert.equal(rendered.renderer.name, "ANSYS_FRAME_2D_BEAM3_V1");
  assert.equal(rendered.mapping.nodeTagPolicy, "IDENTITY");
  assert.equal(rendered.mapping.frameElementTagPolicy, "IDENTITY");
  assert.equal(rendered.mapping.auxiliaryMassElements.length, 1);
  assert.match(rendered.artifacts.modelSha256, /^[0-9a-f]{64}$/);
  assert.match(rendered.artifacts.bundleFingerprint, /^[0-9a-f]{64}$/);
  assert.match(rendered.renderFingerprint, /^[0-9a-f]{64}$/);

  const source = await readFile(rendered.artifacts.modelPath, "utf8");
  assert.match(source, /ET,1,BEAM3/);
  assert.match(source, /ET,2,MASS21/);
  assert.equal(source.includes("ACEL,"), false);
  assert.equal(source.includes("DELTIM,"), false);
});

test("PR33 exposes one SAFE ANSYS model render tool and no execution shortcut", async () => {
  const extension = await readFile(
    ".pi/extensions/model-spec-tools.ts",
    "utf8",
  );
  const solverTools = await readFile(".pi/extensions/fem-tools.ts", "utf8");
  const main = await readFile("apps/agent/src/main.ts", "utf8");

  assert.match(extension, /name:\s*"fem_model_render_ansys"/);
  assert.match(extension, /BEAM3/);
  assert.match(extension, /never calls fem_solver_run/i);
  assert.doesNotMatch(extension, /runFemSolverRun/);
  assert.match(main, /"fem_model_render_ansys"/);
  assert.match(solverTools, /renderManifestPath/);
  assert.match(solverTools, /MACHINE_PROVEN_RENDER_BINDING/);
  assert.match(solverTools, /NOT_MACHINE_PROVEN/);
});
