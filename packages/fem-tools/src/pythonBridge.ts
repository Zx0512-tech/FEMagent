import { spawn } from "node:child_process";

const MAX_OUTPUT_BYTES = 1024 * 1024;

export interface FemHealth {
  status: "ok";
  core: "fem_core";
  coreVersion: string;
  python: {
    version: string;
    implementation: string;
  };
  platform: string;
  solvers: {
    ansys: "not_checked";
    opensees: "not_checked";
  };
}

function pythonExecutable(): string {
  const configured = process.env.FEM_PYTHON?.trim();
  if (configured) return configured;
  return process.platform === "win32" ? "python" : "python3";
}

export async function runFemCoreCommand<T>(
  cwd: string,
  args: readonly string[],
  signal?: AbortSignal,
): Promise<T> {
  return await new Promise<T>((resolve, reject) => {
    const child = spawn(pythonExecutable(), ["-m", "fem_core.cli", ...args], {
      cwd,
      env: process.env,
      windowsHide: true,
      signal,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    let settled = false;

    const fail = (error: Error) => {
      if (settled) return;
      settled = true;
      reject(error);
    };

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");

    child.stdout.on("data", (chunk: string) => {
      stdout += chunk;
      if (Buffer.byteLength(stdout, "utf8") > MAX_OUTPUT_BYTES) {
        child.kill();
        fail(new Error("fem_core stdout exceeded the 1 MiB bootstrap limit"));
      }
    });

    child.stderr.on("data", (chunk: string) => {
      stderr += chunk;
      if (Buffer.byteLength(stderr, "utf8") > MAX_OUTPUT_BYTES) {
        child.kill();
        fail(new Error("fem_core stderr exceeded the 1 MiB bootstrap limit"));
      }
    });

    child.on("error", (error) => {
      fail(new Error(`Unable to start FEM Python core: ${error.message}`));
    });

    child.on("close", (code) => {
      if (settled) return;
      if (code !== 0) {
        fail(new Error(`fem_core exited with code ${code}: ${stderr.trim() || "no stderr"}`));
        return;
      }

      try {
        const parsed = JSON.parse(stdout.trim()) as T;
        settled = true;
        resolve(parsed);
      } catch (error) {
        fail(new Error(`fem_core returned invalid JSON: ${(error as Error).message}`));
      }
    });
  });
}

export async function runFemHealth(cwd: string, signal?: AbortSignal): Promise<FemHealth> {
  return await runFemCoreCommand<FemHealth>(cwd, ["health"], signal);
}
