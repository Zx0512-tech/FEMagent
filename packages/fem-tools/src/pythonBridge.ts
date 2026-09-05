import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";

import {
  DEFAULT_BRIDGE_TIMEOUT_MS,
  DEFAULT_SOLVER_RUN_TIMEOUT_MS,
  FEM_BRIDGE_PROTOCOL,
  type FemBridgeEnvelope,
  type FemHealth,
  type FemLoadInspection,
  type FemStandardizedLoad,
} from "./bridgeProtocol.js";
import type { FemEngineeringEvidenceReport } from "./evidenceTypes.js";
import type { FemAnyModelInspection } from "./modelTypes.js";
import type {
  FemResultManifest,
  FemResultQuery,
  FemResultQueryRequest,
} from "./resultTypes.js";
import type {
  FemRoleEvidenceQueryRequest,
  FemSemanticRoleInspection,
  FemSemanticRoleResolution,
} from "./semanticTypes.js";
import type {
  FemSolverKey,
  FemSolverOptions,
  FemSolverPreflight,
  FemSolverRun,
  FemSolverStatus,
} from "./solverTypes.js";
import type {
  FemCrossSolverQueryRequest,
  FemCrossSolverSideRequest,
  FemCrossSolverValidationReport,
} from "./validationTypes.js";

const MAX_OUTPUT_BYTES = 1024 * 1024;

export class FemBridgeError extends Error {
  constructor(public readonly code: string, message: string) {
    super(message);
    this.name = "FemBridgeError";
  }
}

export class FemCoreError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly details: Record<string, unknown>,
  ) {
    super(message);
    this.name = "FemCoreError";
  }
}

export interface FemBridgeOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  requestId?: string;
}

function pythonExecutable(): string {
  const configured = process.env.FEM_PYTHON?.trim();
  if (configured) return configured;
  return process.platform === "win32" ? "python" : "python3";
}

function parseEnvelope<T>(raw: string, requestId: string): FemBridgeEnvelope<T> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    throw new FemBridgeError("INVALID_BRIDGE_JSON", `fem_core returned invalid JSON: ${(error as Error).message}`);
  }
  if (!parsed || typeof parsed !== "object") {
    throw new FemBridgeError("INVALID_BRIDGE_ENVELOPE", "fem_core response must be a JSON object");
  }
  const envelope = parsed as Partial<FemBridgeEnvelope<T>>;
  if (envelope.protocol !== FEM_BRIDGE_PROTOCOL) {
    throw new FemBridgeError("PROTOCOL_MISMATCH", "fem_core returned an unsupported bridge protocol");
  }
  if (envelope.requestId !== requestId) {
    throw new FemBridgeError("REQUEST_ID_MISMATCH", "fem_core response requestId does not match the request");
  }
  if (typeof envelope.ok !== "boolean") {
    throw new FemBridgeError("INVALID_BRIDGE_ENVELOPE", "fem_core response is missing the ok flag");
  }
  return envelope as FemBridgeEnvelope<T>;
}

export async function runFemCoreRequest<T>(
  cwd: string,
  command: string,
  payload: Record<string, unknown> = {},
  options: FemBridgeOptions = {},
): Promise<T> {
  const requestId = options.requestId ?? randomUUID();
  const timeoutMs = options.timeoutMs ?? Number(process.env.FEM_CORE_TIMEOUT_MS || DEFAULT_BRIDGE_TIMEOUT_MS);
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new FemBridgeError("INVALID_TIMEOUT", "FEM bridge timeout must be a positive finite number");
  }

  return await new Promise<T>((resolve, reject) => {
    const child = spawn(pythonExecutable(), ["-m", "fem_core.cli", "bridge"], {
      cwd,
      env: process.env,
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    let settled = false;
    let timer: NodeJS.Timeout | undefined;

    const cleanup = () => {
      if (timer) clearTimeout(timer);
      options.signal?.removeEventListener("abort", onAbort);
    };
    const fail = (error: Error) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(error);
    };
    const onAbort = () => {
      child.kill();
      fail(new FemBridgeError("BRIDGE_ABORTED", "FEM bridge request was aborted"));
    };

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      stdout += chunk;
      if (Buffer.byteLength(stdout, "utf8") > MAX_OUTPUT_BYTES) {
        child.kill();
        fail(new FemBridgeError("BRIDGE_OUTPUT_TOO_LARGE", "fem_core stdout exceeded the 1 MiB bridge limit"));
      }
    });
    child.stderr.on("data", (chunk: string) => {
      stderr += chunk;
      if (Buffer.byteLength(stderr, "utf8") > MAX_OUTPUT_BYTES) {
        child.kill();
        fail(new FemBridgeError("BRIDGE_OUTPUT_TOO_LARGE", "fem_core stderr exceeded the 1 MiB bridge limit"));
      }
    });
    child.on("error", (error) => fail(new FemBridgeError("BRIDGE_START_FAILED", `Unable to start FEM Python core: ${error.message}`)));
    child.on("close", (code) => {
      if (settled) return;
      if (code !== 0) {
        fail(new FemBridgeError("BRIDGE_PROCESS_FAILED", `fem_core exited with code ${code}: ${stderr.trim() || "no stderr"}`));
        return;
      }
      try {
        const envelope = parseEnvelope<T>(stdout.trim(), requestId);
        if (!envelope.ok) {
          fail(new FemCoreError(envelope.error.code, envelope.error.message, envelope.error.details));
          return;
        }
        settled = true;
        cleanup();
        resolve(envelope.result);
      } catch (error) {
        fail(error as Error);
      }
    });

    if (options.signal?.aborted) {
      onAbort();
      return;
    }
    options.signal?.addEventListener("abort", onAbort, { once: true });
    timer = setTimeout(() => {
      child.kill();
      fail(new FemBridgeError("BRIDGE_TIMEOUT", `fem_core request exceeded ${timeoutMs} ms`));
    }, timeoutMs);

    child.stdin.end(JSON.stringify({ protocol: FEM_BRIDGE_PROTOCOL, requestId, command, payload }));
  });
}

export async function runFemHealth(cwd: string, signal?: AbortSignal): Promise<FemHealth> {
  return await runFemCoreRequest<FemHealth>(cwd, "health", {}, { signal });
}

export async function runFemModelInspect(cwd: string, path: string, signal?: AbortSignal): Promise<FemAnyModelInspection> {
  return await runFemCoreRequest<FemAnyModelInspection>(cwd, "model.inspect", { path }, { signal });
}

export async function runFemLoadInspect(cwd: string, path: string, signal?: AbortSignal): Promise<FemLoadInspection> {
  return await runFemCoreRequest<FemLoadInspection>(cwd, "load.inspect", { path }, { signal });
}

export async function runFemLoadStandardize(
  cwd: string,
  path: string,
  mapping: Record<string, unknown>,
  outputPath?: string,
  signal?: AbortSignal,
): Promise<FemStandardizedLoad> {
  return await runFemCoreRequest<FemStandardizedLoad>(
    cwd,
    "load.standardize",
    { path, mapping, ...(outputPath ? { outputPath } : {}) },
    { signal },
  );
}

export async function runFemSemanticInspect(
  cwd: string,
  modelPath: string,
  manifestPath: string,
  signal?: AbortSignal,
): Promise<FemSemanticRoleInspection> {
  return await runFemCoreRequest<FemSemanticRoleInspection>(
    cwd,
    "semantic.inspect",
    { modelPath, manifestPath },
    { signal },
  );
}

export async function runFemSemanticResolve(
  cwd: string,
  modelPath: string,
  manifestPath: string,
  roleId: string,
  signal?: AbortSignal,
): Promise<FemSemanticRoleResolution> {
  return await runFemCoreRequest<FemSemanticRoleResolution>(
    cwd,
    "semantic.resolve",
    { modelPath, manifestPath, roleId },
    { signal },
  );
}

export async function runFemResultInspect(
  cwd: string,
  runRef: string,
  signal?: AbortSignal,
): Promise<FemResultManifest> {
  return await runFemCoreRequest<FemResultManifest>(cwd, "result.inspect", { runRef }, { signal });
}

export async function runFemResultQuery(
  cwd: string,
  runRef: string,
  query: FemResultQueryRequest,
  signal?: AbortSignal,
): Promise<FemResultQuery> {
  return await runFemCoreRequest<FemResultQuery>(cwd, "result.query", { runRef, query }, { signal });
}

export async function runFemEvidenceProject(
  cwd: string,
  projectId: string,
  runRef: string,
  evidenceId: string,
  query: FemResultQueryRequest,
  signal?: AbortSignal,
): Promise<FemEngineeringEvidenceReport> {
  return await runFemCoreRequest<FemEngineeringEvidenceReport>(
    cwd,
    "evidence.project",
    { projectId, runRef, evidenceId, query },
    { signal },
  );
}

export async function runFemRoleEvidenceProject(
  cwd: string,
  projectId: string,
  modelPath: string,
  manifestPath: string,
  roleId: string,
  runRef: string,
  evidenceId: string,
  query: FemRoleEvidenceQueryRequest,
  signal?: AbortSignal,
): Promise<FemEngineeringEvidenceReport> {
  return await runFemCoreRequest<FemEngineeringEvidenceReport>(
    cwd,
    "evidence.projectRole",
    { projectId, modelPath, manifestPath, roleId, runRef, evidenceId, query },
    { signal },
  );
}

export async function runFemCrossSolverValidation(
  cwd: string,
  projectId: string,
  left: FemCrossSolverSideRequest,
  right: FemCrossSolverSideRequest,
  query: FemCrossSolverQueryRequest,
  signal?: AbortSignal,
): Promise<FemCrossSolverValidationReport> {
  return await runFemCoreRequest<FemCrossSolverValidationReport>(
    cwd,
    "validation.crossSolver",
    { projectId, left, right, query },
    { signal },
  );
}

export async function runFemSolverStatus<S extends FemSolverKey>(
  cwd: string,
  solver: S,
  signal?: AbortSignal,
): Promise<FemSolverStatus<S>> {
  return await runFemCoreRequest<FemSolverStatus<S>>(cwd, "solver.status", { solver }, { signal });
}

export async function runFemSolverPreflight<S extends FemSolverKey>(
  cwd: string,
  solver: S,
  modelPath: string,
  loadPath?: string,
  solverOptions?: FemSolverOptions,
  signal?: AbortSignal,
): Promise<FemSolverPreflight<S>> {
  return await runFemCoreRequest<FemSolverPreflight<S>>(
    cwd,
    "solver.preflight",
    {
      solver,
      modelPath,
      ...(loadPath ? { loadPath } : {}),
      ...(solverOptions ? { solverOptions } : {}),
    },
    { signal },
  );
}

export async function runFemSolverRun<S extends FemSolverKey>(
  cwd: string,
  solver: S,
  modelPath: string,
  loadPath?: string,
  solverOptions?: FemSolverOptions,
  signal?: AbortSignal,
): Promise<FemSolverRun<S>> {
  return await runFemCoreRequest<FemSolverRun<S>>(
    cwd,
    "solver.run",
    {
      solver,
      modelPath,
      ...(loadPath ? { loadPath } : {}),
      ...(solverOptions ? { solverOptions } : {}),
    },
    { signal, timeoutMs: DEFAULT_SOLVER_RUN_TIMEOUT_MS },
  );
}
