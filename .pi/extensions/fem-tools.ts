import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runFemHealth,
  runFemLoadInspect,
  runFemLoadStandardize,
  runFemModelInspect,
} from "@femagent/fem-tools";
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
    description: "Deterministically inspect CSV/TXT/DAT/XLSX or PEER NGA AT1/AT2 engineering load data, returning a LoadManifest and a non-binding mapping suggestion. The tool never applies the load to a solver.",
    promptSnippet: "Inspect engineering load files before choosing mappings, units or solver application semantics",
    promptGuidelines: [
      "Use fem_load_inspect before making claims about unfamiliar load data.",
      "suggestedMapping is a candidate, not engineering truth. Never silently promote guessed units or directions into an executable mapping.",
      "PEER headers can establish sampling interval and acceleration unit, but excitation component/direction still requires project evidence or user confirmation.",
      "Use manifest.time and requiredConfirmations to decide what must be clarified before standardization.",
    ],
    parameters: Type.Object({ path: Type.String({ description: "Workspace-relative load file path" }) }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemLoadInspect(ctx.cwd, params.path, signal);
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });

  pi.registerTool({
    name: "fem_load_standardize",
    label: "Standardize FEM Load",
    description: "Convert a confirmed load mapping into FEMagent canonical long-form CSV using deterministic time validation and unit conversion. This writes a generated file inside the active workspace and does not run a solver.",
    promptSnippet: "Standardize a user-confirmed engineering load mapping before solver execution",
    promptGuidelines: [
      "Call fem_load_standardize only after the mapping contains explicit loadKind, time information, value column, quantity, sourceUnit, applicationType and component for every channel.",
      "Do not pass unresolved suggestedMapping fields such as null component or magnitude-guessed units without confirmation.",
      "Treat the returned SHA256 and standardized output path as the deterministic load artifact precursor for later solver/evidence stages.",
    ],
    parameters: Type.Object({
      path: Type.String({ description: "Workspace-relative source load file path" }),
      mapping: Type.Record(Type.String(), Type.Unknown(), { description: "Explicit confirmed load mapping" }),
      outputPath: Type.Optional(Type.String({ description: "Optional workspace-relative output CSV path" })),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemLoadStandardize(ctx.cwd, params.path, params.mapping, params.outputPath, signal);
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });
}
