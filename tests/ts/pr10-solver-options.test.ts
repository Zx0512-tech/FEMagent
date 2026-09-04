import assert from "node:assert/strict";
import test from "node:test";

import { FemCoreError, runFemSolverPreflight } from "@femagent/fem-tools";

const cwd = process.cwd();

test("solverOptions cross the TypeScript bridge and OpenSees rejects ANSYS modelUnits", async () => {
  await assert.rejects(
    () =>
      runFemSolverPreflight(
        cwd,
        "opensees",
        "tests/fixtures/does-not-need-to-exist.json",
        undefined,
        { modelUnits: { length: "mm", time: "s" } },
      ),
    (error: unknown) => error instanceof FemCoreError && error.code === "UNSUPPORTED_SOLVER_OPTIONS",
  );
});
