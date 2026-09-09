import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function source(path: string): Promise<string> {
  return await readFile(path, "utf8");
}

test("one high-level OpenSees analysis preparation tool owns CHECK and RENDER", async () => {
  const extension = await source(".pi/extensions/analysis-spec-tools.ts");

  assert.match(extension, /name:\s*"fem_analysis_prepare_opensees"/);
  assert.match(extension, /Type\.Union\(\[Type\.Literal\("CHECK"\), Type\.Literal\("RENDER"\)\]\)/s);
  assert.match(extension, /analysisSpec:\s*analysisSpecV1Schema/);
  assert.match(extension, /runFemAnalysisReadiness/);
  assert.match(extension, /runFemAnalysisRenderOpenSees/);
  assert.match(extension, /V1 remains limited/i);
  assert.doesNotMatch(extension, /runFemSolverRun/);
  assert.doesNotMatch(extension, /outputPath/);
  assert.doesNotMatch(extension, /name:\s*"fem_analysis_readiness"/);
  assert.doesNotMatch(extension, /name:\s*"fem_analysis_render_opensees"/);
});

test("analysis preparation guidance preserves readiness/render/execution boundaries", async () => {
  const extension = await source(".pi/extensions/analysis-spec-tools.ts");

  assert.match(extension, /CHECK is read-only/i);
  assert.match(extension, /RENDER writes only controlled artifacts/i);
  assert.match(extension, /neither runs a solver/i);
  assert.match(extension, /READY.*not.*execution success/is);
  assert.match(extension, /RENDERED.*not.*execution success/is);
  assert.match(extension, /do not.*mutate.*engineering facts.*force readiness/is);
  assert.match(extension, /schemaVersion 1\.0|V1.*only/i);
});

test("agent entrypoint exposes the single high-level Analysis preparation tool", async () => {
  const main = await source("apps/agent/src/main.ts");

  assert.match(main, /"fem_analysis_prepare_opensees"/);
  assert.doesNotMatch(main, /"fem_analysis_readiness"/);
  assert.doesNotMatch(main, /"fem_analysis_render_opensees"/);
  assert.doesNotMatch(main, /fem_analysis_spec_migrate/i);
});
