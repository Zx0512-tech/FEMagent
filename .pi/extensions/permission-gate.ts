import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function permissionGate(pi: ExtensionAPI) {
  pi.on("tool_call", async (event, ctx) => {
    if (event.toolName !== "fem_solver_run") return;

    const input = event.input as Record<string, unknown>;
    const solver = typeof input.solver === "string" ? input.solver : "unknown solver";
    const modelPath = typeof input.modelPath === "string" ? input.modelPath : "unknown model";
    const loadPath = typeof input.loadPath === "string" ? input.loadPath : "unknown load";

    if (!ctx.hasUI) {
      return {
        block: true,
        reason: "Real FEM solver execution requires an interactive/RPC user confirmation surface.",
      };
    }

    const approved = await ctx.ui.confirm(
      "Run real FEM analysis?",
      `Execute ${solver} with model '${modelPath}' and load '${loadPath}'?`,
    );
    if (!approved) {
      return { block: true, reason: "User declined real FEM solver execution." };
    }
  });
}
