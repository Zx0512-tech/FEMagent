import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { runFemHealth, runFemLoadInspect, runFemModelInspect } from "@femagent/fem-tools";
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
      return { content: [{ type: "text", text: JSON.stringify(health, null, 2) }], details: health };
    },
  });

  pi.registerTool({
    name: "fem_model_inspect",
    label: "Inspect FEM Model",
    description: "Deterministically inspect an ANSYS APDL/CDB-style model inside the active workspace and return validation evidence plus a normalized FEMModelManifest. The tool never executes a solver.",
    promptSnippet: "Inspect unfamiliar FEM models and reason from their normalized manifest",
    promptGuidelines: [
      "Use fem_model_inspect before making claims about an unfamiliar FEM model.",
      "Treat manifest values as static inspection evidence; null topology counts mean the final model must be enumerated by a later solver-inspection tool.",
      "If executionEligibility is REJECTED, never execute the model. If it is INCOMPLETE, explain the missing structural signals instead of pretending the model is runnable.",
      "Component names are hints only and do not prove engineering roles such as girder, tower, bearing, or damper location.",
      "Do not hard-code X/Y/Z as longitudinal/transverse/vertical unless the project or user establishes that convention.",
    ],
    parameters: Type.Object({ path: Type.String({ description: "Workspace-relative FEM model file path" }) }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemModelInspect(ctx.cwd, params.path, signal);
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });

  pi.registerTool({
    name: "fem_load_inspect",
    label: "Inspect FEM Load",
    description: "Deterministically inspect a tabular engineering load file inside the active workspace. Current support is CSV/TXT/DAT and the tool does not assign engineering meaning or units automatically.",
    promptSnippet: "Inspect engineering load data before deciding mappings or units",
    promptGuidelines: [
      "Use fem_load_inspect before making claims about unfamiliar load data.",
      "A timeCandidate is a deterministic column-name hint only; confirm ambiguous mappings with the user or later mapping tools.",
      "Never invent load units, directions, target nodes, or load kinds from numeric values alone.",
    ],
    parameters: Type.Object({ path: Type.String({ description: "Workspace-relative load file path" }) }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemLoadInspect(ctx.cwd, params.path, signal);
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });
}
