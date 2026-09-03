import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runFemHealth,
  runFemLoadInspect,
  runFemLoadStandardize,
  runFemModelInspect,
  runFemSolverPreflight,
  runFemSolverRun,
  runFemSolverStatus,
} from "@femagent/fem-tools";
import { Type } from "typebox";

const solverName = Type.Union([Type.Literal("opensees")], {
  description: "Concrete FEM solver adapter. PR5 supports opensees only.",
});

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

  pi.registerTool({
    name: "fem_solver_status",
    label: "FEM Solver Status",
    description: "Check installation and declared capabilities of a concrete SolverAdapter without running a finite-element analysis.",
    promptSnippet: "Check concrete solver availability before preflight or execution",
    promptGuidelines: [
      "Use fem_solver_status when solver availability is unknown; fem_health does not prove a solver is installed.",
    ],
    parameters: Type.Object({ solver: solverName }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemSolverStatus(ctx.cwd, params.solver, signal);
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });

  pi.registerTool({
    name: "fem_solver_preflight",
    label: "Preflight FEM Solver",
    description: "Validate solver availability plus deterministic model/load compatibility without performing the requested finite-element solve.",
    promptSnippet: "Preflight the concrete FEM solver with explicit model and canonical load artifacts",
    promptGuidelines: [
      "Call fem_solver_preflight before fem_solver_run and resolve BLOCKED checks before requesting execution.",
      "PR5 OpenSees preflight accepts only the controlled ELASTIC_SDOF model spec and a single canonical EARTHQUAKE UNIFORM_EXCITATION acceleration channel.",
    ],
    parameters: Type.Object({
      solver: solverName,
      modelPath: Type.String({ description: "Workspace-relative solver model-spec path" }),
      loadPath: Type.String({ description: "Workspace-relative FEMAGENT_LOAD_CSV_V1 path" }),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemSolverPreflight(ctx.cwd, params.solver, params.modelPath, params.loadPath, signal);
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });

  pi.registerTool({
    name: "fem_solver_run",
    label: "Run FEM Solver",
    description: "Execute a real finite-element solver through its isolated SolverAdapter worker and return a run manifest with real solver outputs. This is an EXECUTION-risk tool and is permission-gated.",
    promptSnippet: "Run a user-approved real FEM analysis only after successful solver preflight",
    promptGuidelines: [
      "Never call fem_solver_run before fem_solver_preflight reports READY.",
      "fem_solver_run is an EXECUTION action. The permission gate must obtain user approval before the solver starts.",
      "Do not describe PR5's controlled ELASTIC_SDOF Golden Path as support for arbitrary uploaded OpenSees Python models.",
    ],
    parameters: Type.Object({
      solver: solverName,
      modelPath: Type.String({ description: "Workspace-relative solver model-spec path" }),
      loadPath: Type.String({ description: "Workspace-relative FEMAGENT_LOAD_CSV_V1 path" }),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemSolverRun(ctx.cwd, params.solver, params.modelPath, params.loadPath, signal);
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });
}
