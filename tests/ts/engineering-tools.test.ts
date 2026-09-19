import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import {
  FEM_BRIDGE_PROTOCOL,
  FemBridgeError,
  FemCoreError,
  runFemCoreRequest,
  runFemLoadInspect,
  runFemLoadStandardize,
  runFemModelInspect,
  runFemResultInspect,
  runFemResultQuery,
  runFemSolverPreflight,
  runFemSolverRun,
  runFemSolverStatus,
  type FemAnsysV2Options,
  type FemSolverOptions,
} from "@femagent/fem-tools";

const cwd = process.cwd();

const ansysV2TypeContract: FemAnsysV2Options = {
  analysisSpec: {
    schemaVersion: "2.0",
    kind: "engineering_analysis_spec",
    modelSpecFingerprint: "a".repeat(64),
    analysisType: "TRANSIENT",
    units: {},
    definition: {
      time: { timeStep: 0.01, duration: 0.02 },
      damping: { type: "NONE" },
      excitation: {
        type: "UNIFORM_BASE_EXCITATION",
        component: "X",
        quantity: "ACCELERATION",
        loadArtifact: {
          path: "loads/eq.csv",
          sha256: "b".repeat(64),
        },
      },
    },
    resultRequests: [
      {
        requestId: "U2X",
        quantity: "DISPLACEMENT",
        target: { type: "NODE", id: 2 },
        component: "X",
      },
    ],
  },
  confirmedBundleFingerprint: "c".repeat(64),
};

const ansysV2SolverOptionsTypeContract: FemSolverOptions = {
  modelUnits: { length: "m", time: "s" },
  ansysV2: ansysV2TypeContract,
};


const earthquakeMapping = {
  version: 1,
  loadKind: "EARTHQUAKE",
  timeColumn: "time_s",
  timeUnit: "s",
  valueColumn: "acceleration_g",
  quantity: "ACCELERATION",
  sourceUnit: "g",
  applicationType: "UNIFORM_EXCITATION",
  component: "X",
  scale: 1.0,
};

function sha256(content: string): string {
  return createHash("sha256").update(content).digest("hex");
}

async function writeSyntheticResultRun(): Promise<{ runId: string; runDir: string }> {
  const runId = `run_ts${randomUUID().replaceAll("-", "").slice(0, 12)}`;
  const relativeRunDir = path.posix.join(".femagent", "runs", runId);
  const runDir = path.join(cwd, relativeRunDir);
  await mkdir(runDir, { recursive: true });

  const response = [
    "time_s,relative_displacement_m,relative_velocity_m_s,relative_acceleration_m_s2",
    "0,0,0,0",
    "0.1,0.02,0.2,1",
    "0.2,-0.03,-0.1,-0.5",
    "0.3,0.01,0,0.25",
    "",
  ].join("\n");
  const summaryObject = {
    responseNode: 2,
    responseDof: 1,
    sampleCount: 4,
    minDisplacementM: -0.03,
    maxDisplacementM: 0.02,
    absolutePeakDisplacementM: 0.03,
    timeAtAbsolutePeakS: 0.2,
  };
  const summary = `${JSON.stringify(summaryObject, null, 2)}\n`;
  const solverLog = "synthetic TypeScript Result Intelligence run\n";
  await writeFile(path.join(runDir, "response.csv"), response, "utf8");
  await writeFile(path.join(runDir, "result_summary.json"), summary, "utf8");
  await writeFile(path.join(runDir, "solver.log"), solverLog, "utf8");

  const outputs = {
    runManifest: path.posix.join(relativeRunDir, "run_manifest.json"),
    responseCsv: path.posix.join(relativeRunDir, "response.csv"),
    responseSha256: sha256(response),
    resultSummary: path.posix.join(relativeRunDir, "result_summary.json"),
    resultSummarySha256: sha256(summary),
    solverLog: path.posix.join(relativeRunDir, "solver.log"),
    solverLogSha256: sha256(solverLog),
  };
  const manifest = {
    schemaVersion: "1.0",
    kind: "solver_run",
    runId,
    caseFingerprint: "a".repeat(64),
    status: "COMPLETED",
    solver: {
      name: "OPENSEESPY",
      packageVersion: "3.8.0.0",
      engineVersion: "3.8.0",
      executionMode: "ISOLATED_WORKER_PROCESS",
    },
    model: { path: "synthetic-model.json", sha256: "b".repeat(64) },
    load: { path: "synthetic-load.csv", sha256: "c".repeat(64) },
    analysis: { type: "TRANSIENT_UNIFORM_EXCITATION" },
    summary: summaryObject,
    outputs,
  };
  await writeFile(path.join(runDir, "run_manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  return { runId, runDir };
}


test("ANSYS V2 uniform-base intent is carried only through typed generic solver options", () => {
  assert.equal(ansysV2SolverOptionsTypeContract.modelUnits?.length, "m");
  assert.equal(ansysV2SolverOptionsTypeContract.ansysV2?.analysisSpec.analysisType, "TRANSIENT");
  assert.equal(
    ansysV2SolverOptionsTypeContract.ansysV2?.analysisSpec.definition.excitation.type,
    "UNIFORM_BASE_EXCITATION",
  );
  assert.equal(ansysV2SolverOptionsTypeContract.ansysV2?.confirmedBundleFingerprint.length, 64);
});

test("PR29 keeps ANSYS V2 behind the existing generic solver tools", async () => {
  const source = await readFile(".pi/extensions/fem-tools.ts", "utf8");
  assert.match(source, /ansysV2/);
  assert.match(source, /confirmedBundleFingerprint/);
  assert.match(source, /semanticEquivalence/);
  assert.doesNotMatch(source, /name:\s*"fem_ansys_v2_/);
  assert.doesNotMatch(source, /name:\s*"fem_earthquake_run"/);
});


test("model inspection crosses the versioned TypeScript/Python bridge", async () => {
  const report = await runFemModelInspect(cwd, "tests/fixtures/simple_model.apdl");
  assert.equal(report.kind, "model_inspection");
  if (report.kind !== "model_inspection") throw new Error("expected ANSYS model inspection");
  assert.equal(report.schemaVersion, "1.1");
  assert.equal(report.summary.explicitNodeCommandCount, 2);
  assert.equal(report.validation.executionEligibility, "STATICALLY_ELIGIBLE");
  assert.deepEqual(report.manifest.topology.elementTypes, [{ id: "1", name: "BEAM188" }]);
  assert.equal(report.manifest.topology.nodeCount.value, 2);
});

test("OpenSees Python bundle inspection crosses the strict JSON bridge", async () => {
  const report = await runFemModelInspect(cwd, "tests/fixtures/opensees_bundle/main.py");
  assert.equal(report.kind, "opensees_python_model_inspection");
  if (report.kind !== "opensees_python_model_inspection") throw new Error("expected OpenSees Python inspection");
  assert.equal(report.classification, "MODEL_CONFIRMED");
  assert.equal(report.bundle.integrity, "VALID");
  assert.ok(report.bundle.files.some((item) => item.path.endsWith("opensees_bundle/materials.py")));
  assert.equal(report.bundle.bundleFingerprint.length, 64);
});

test("load inspection crosses the versioned TypeScript/Python bridge", async () => {
  const report = await runFemLoadInspect(cwd, "tests/fixtures/earthquake.csv");
  assert.equal(report.kind, "load_inspection");
  assert.equal(report.rowCount, 4);
  assert.equal(report.columns[0]?.timeCandidate, true);
});

test("load standardization crosses the bridge with explicit confirmed mapping", async () => {
  const report = await runFemLoadStandardize(cwd, "tests/fixtures/earthquake.csv", earthquakeMapping);
  assert.equal(report.kind, "standardized_load");
  assert.equal(report.format, "FEMAGENT_LOAD_CSV_V1");
  assert.equal(report.channels[0]?.standardUnit, "m/s2");
});

test("OpenSees status, preflight and real solve cross the strict JSON bridge", async () => {
  const status = await runFemSolverStatus(cwd, "opensees");
  assert.equal(status.solver, "OPENSEESPY");
  assert.equal(status.available, true);

  const load = await runFemLoadStandardize(cwd, "tests/fixtures/earthquake.csv", earthquakeMapping);
  const preflight = await runFemSolverPreflight(
    cwd,
    "opensees",
    "tests/fixtures/opensees_sdof.json",
    load.output.path,
  );
  assert.equal(preflight.status, "READY");
  assert.equal(preflight.executionEstimate.analysisSteps, 3);

  const run = await runFemSolverRun(
    cwd,
    "opensees",
    "tests/fixtures/opensees_sdof.json",
    load.output.path,
  );
  assert.equal(run.status, "COMPLETED");
  assert.equal(run.solver.name, "OPENSEESPY");
  const peak = run.summary.absolutePeakDisplacementM;
  assert.equal(typeof peak, "number");
  if (typeof peak !== "number") throw new Error("expected numeric peak displacement");
  assert.ok(peak > 0);
});

test("OpenSees Python bundle preflight and run use the existing generic solver tool contract", async () => {
  const modelPath = "tests/fixtures/opensees_bundle/main.py";
  const preflight = await runFemSolverPreflight(cwd, "opensees", modelPath);
  assert.equal(preflight.status, "READY");
  assert.equal(preflight.model.format, "OPENSEES_PYTHON");
  assert.equal(preflight.load.mode, "MODEL_SCRIPT_MANAGED");

  const run = await runFemSolverRun(cwd, "opensees", modelPath);
  assert.equal(run.status, "COMPLETED");
  assert.equal(run.model.format, "OPENSEES_PYTHON");
  assert.equal(run.analysis.type, "MODEL_SCRIPT");
  assert.equal(run.summary.nodeCount, 2);
  assert.equal(run.summary.elementCount, 1);
});

test("ANSYS status and fail-closed preflight use the generic solver bridge contract", async () => {
  const previous = process.env.FEM_ANSYS_EXECUTABLE;
  process.env.FEM_ANSYS_EXECUTABLE = "tests/fixtures/definitely-missing-ansys-runtime";
  try {
    const status = await runFemSolverStatus(cwd, "ansys");
    const statusSolver: "ANSYS" = status.solver;
    assert.equal(statusSolver, "ANSYS");
    assert.equal(status.available, false);

    const preflight = await runFemSolverPreflight(cwd, "ansys", "tests/fixtures/simple_model.apdl");
    const preflightSolver: "ANSYS" = preflight.solver;
    assert.equal(preflightSolver, "ANSYS");
    assert.equal(preflight.status, "BLOCKED");
    assert.ok(preflight.checks.some((check) => check.code === "SOLVER_AVAILABLE" && check.status === "FAILED"));
  } finally {
    if (previous === undefined) delete process.env.FEM_ANSYS_EXECUTABLE;
    else process.env.FEM_ANSYS_EXECUTABLE = previous;
  }
});

test("Result Intelligence inspect and query cross the read-only bridge", async () => {
  const { runId, runDir } = await writeSyntheticResultRun();
  try {
    const inspection = await runFemResultInspect(cwd, runId);
    assert.equal(inspection.kind, "result_manifest");
    assert.equal(inspection.integrity.status, "VALID");
    assert.ok(inspection.queryCapabilities.some((item) => item.quantity === "DISPLACEMENT"));

    const query = await runFemResultQuery(cwd, runId, {
      quantity: "DISPLACEMENT",
      target: { type: "NODE", id: 2 },
      component: "UX",
      operation: "SUMMARY",
    });
    assert.equal(query.kind, "result_query");
    assert.equal(query.component, "X");
    assert.equal(query.unit, "m");
    assert.equal(query.summary?.absolutePeak, 0.03);
    assert.equal(query.summary?.abscissaAtAbsolutePeak, 0.2);
  } finally {
    await rm(runDir, { recursive: true, force: true });
  }
});

test("Python domain errors preserve stable error codes", async () => {
  await assert.rejects(
    () => runFemModelInspect(cwd, "tests/fixtures/missing.apdl"),
    (error: unknown) => error instanceof FemCoreError && error.code === "FILE_NOT_FOUND",
  );
});

test("bridge request exposes protocol version and enforces timeout", async () => {
  assert.equal(FEM_BRIDGE_PROTOCOL, "femagent.bridge/v1");
  await assert.rejects(
    () => runFemCoreRequest(cwd, "health", {}, { timeoutMs: 1 }),
    (error: unknown) => error instanceof FemBridgeError && error.code === "BRIDGE_TIMEOUT",
  );
});
