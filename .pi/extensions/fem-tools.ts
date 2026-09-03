import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { runFemHealth } from "@femagent/fem-tools";
import { Type } from "typebox";

export default function femToolsExtension(pi: ExtensionAPI) {
  pi.registerTool({
    name: "fem_health",
    label: "FEM Health",
    description: "Check whether the deterministic FEMagent Python core bridge is available. This does not validate ANSYS or OpenSees.",
    promptSnippet: "Check the FEMagent deterministic Python core runtime status",
    promptGuidelines: [
      "Use fem_health to verify the FEMagent Python core bridge; never interpret not_checked solver fields as solver availability.",
    ],
    parameters: Type.Object({}),
    async execute(_toolCallId, _params, signal, _onUpdate, ctx) {
      const health = await runFemHealth(ctx.cwd, signal);
      return {
        content: [{ type: "text", text: JSON.stringify(health, null, 2) }],
        details: health,
      };
    },
  });
}
