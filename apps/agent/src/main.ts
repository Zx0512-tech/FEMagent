import { resolve } from "node:path";

import {
  createAgentSession,
  DefaultResourceLoader,
  SessionManager,
} from "@earendil-works/pi-coding-agent";

const cwd = process.cwd();
const prompt = process.argv.slice(2).join(" ").trim()
  || "Call fem_health exactly once, then summarize the FEM runtime status without claiming any solver has been validated.";

const resourceLoader = new DefaultResourceLoader({
  cwd,
  agentDir: process.env.PI_AGENT_DIR || resolve(cwd, ".pi"),
  additionalExtensionPaths: [
    resolve(cwd, ".pi/extensions/fem-tools.ts"),
    resolve(cwd, ".pi/extensions/permission-gate.ts"),
    resolve(cwd, ".pi/extensions/knowledge-tools.ts"),
    resolve(cwd, ".pi/extensions/model-spec-tools.ts"),
  ],
});
await resourceLoader.reload();

const { session } = await createAgentSession({
  cwd,
  resourceLoader,
  sessionManager: SessionManager.inMemory(cwd),
  tools: [
    "read",
    "grep",
    "find",
    "ls",
    "engiknow_search",
    "fem_health",
    "fem_model_inspect",
    "fem_model_spec_validate",
    "fem_model_spec_readiness",
    "fem_model_render_opensees",
    "fem_load_inspect",
    "fem_load_standardize",
    "fem_solver_status",
    "fem_solver_preflight",
    "fem_solver_run",
  ],
});

session.subscribe((event) => {
  if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
    process.stdout.write(event.assistantMessageEvent.delta);
  }
});

try {
  await session.prompt(prompt);
  process.stdout.write("\n");
} finally {
  session.dispose();
}
