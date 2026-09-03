import assert from "node:assert/strict";
import test from "node:test";

import { runFemHealth } from "@femagent/fem-tools";

test("TypeScript bridge receives deterministic FEM core health JSON", async () => {
  const health = await runFemHealth(process.cwd());

  assert.equal(health.status, "ok");
  assert.equal(health.core, "fem_core");
  assert.equal(health.coreVersion, "0.1.0");
  assert.equal(health.solvers.ansys, "not_checked");
  assert.equal(health.solvers.opensees, "not_checked");
});
