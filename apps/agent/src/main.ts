import { resolve } from "node:path";

import {
  createAgentSession,
  DefaultResourceLoader,
  getAgentDir,
  SessionManager,
} from "@earendil-works/pi-coding-agent";

const cwd = process.cwd();
const prompt = process.argv.slice(2).join(" ").trim()
  || "Call fem_health exactly once, then summarize the FEM runtime status without claiming any solver has been validated.";

const resourceLoader = new DefaultResourceLoader({
  cwd,
  agentDir: getAgentDir(),
  additionalExtensionPaths: [resolve(cwd, ".pi/extensions/fem-tools.ts")],
});
await resourceLoader.reload();

const { session } = await createAgentSession({
  cwd,
  resourceLoader,
  sessionManager: SessionManager.inMemory(cwd),
  tools: ["read", "grep", "find", "ls", "fem_health"],
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
