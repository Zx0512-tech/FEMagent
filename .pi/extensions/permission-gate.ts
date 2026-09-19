import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

function executionContext(input: Record<string, unknown>): string {
  const options = input.solverOptions;
  if (!options || typeof options !== "object") return "";
  const solverOptions = options as Record<string, unknown>;
  const ansysV2 = solverOptions.ansysV2;
  if (ansysV2 && typeof ansysV2 === "object") {
    const v2 = ansysV2 as Record<string, unknown>;
    const spec = v2.analysisSpec;
    const fingerprint = typeof v2.confirmedBundleFingerprint === "string"
      ? v2.confirmedBundleFingerprint
      : "";
    if (spec && typeof spec === "object") {
      const analysisSpec = spec as Record<string, unknown>;
      const definition = analysisSpec.definition;
      const details = definition && typeof definition === "object"
        ? definition as Record<string, unknown>
        : {};
      const excitation = details.excitation && typeof details.excitation === "object"
        ? details.excitation as Record<string, unknown>
        : {};
      const time = details.time && typeof details.time === "object"
        ? details.time as Record<string, unknown>
        : {};
      return [
        `Analysis: ${String(analysisSpec.analysisType ?? "unknown")}`,
        `Excitation: ${String(excitation.component ?? "?")}-direction ${String(excitation.type ?? "unknown")}`,
        `dt/duration: ${String(time.timeStep ?? "?")} / ${String(time.duration ?? "?")}`,
        fingerprint ? `APDL bundle: ${fingerprint.slice(0, 12)}…` : "",
      ].filter(Boolean).join("\n");
    }
  }
  const manifest = solverOptions.analysisManifestPath;
  if (typeof manifest === "string" && manifest) {
    return `Generated analysis manifest: ${manifest}`;
  }
  return "";
}

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

    const context = executionContext(input);
    const approved = await ctx.ui.confirm(
      "Run real FEM analysis?",
      [
        `Execute ${solver} with model '${modelPath}' and load '${loadPath}'?`,
        context,
      ].filter(Boolean).join("\n"),
    );
    if (!approved) {
      return { block: true, reason: "User declined real FEM solver execution." };
    }
  });
}
