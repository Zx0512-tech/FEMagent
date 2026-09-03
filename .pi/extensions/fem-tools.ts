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
    description: "Deterministically inspect an unfamiliar FEM model file inside the active workspace. PR2 supports ANSYS APDL/CDB-style text only and does not execute a solver.",
    promptSnippet: "Inspect FEM model files before making claims about their structure",
    promptGuidelines: [
      "Use fem_model_inspect before claiming facts about an unfamiliar FEM model.",
      "Treat explicit command counts as static text evidence, not total model node or element counts.",
      "Do not infer bridge components, coordinate semantics, or solver validity unless the inspection result proves them.",
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
    description: "Deterministically inspect a tabular engineering load file inside the active workspace. PR2 supports CSV/TXT/DAT and does not assign engineering meaning or units automatically.",
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
