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

const solverName = Type.Union([Type.Literal("opensees"), Type.Literal("ansys")], {
  description: "Concrete FEM solver adapter. Current support is OpenSeesPy and ANSYS MAPDL.",
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
    description: "Deterministically inspect an ANSYS APDL/CDB-style model bundle or an OpenSees Python model bundle inside the active workspace. Static inspection never runs the requested analysis.",
    promptSnippet: "Inspect unfamiliar FEM model entrypoints and reason from normalized static/bundle evidence",
    promptGuidelines: [
      "Use fem_model_inspect before making claims about an unfamiliar FEM model.",
      "A model may span multiple files. For ANSYS and OpenSees, treat bundleFingerprint plus bundle files as model identity rather than the entrypoint SHA alone.",
      "ANSYS .txt/.dat entrypoints are models only when deterministic APDL/CDB signals are present; do not classify arbitrary text data as a model.",
      "Static facts are not always realized solver topology; dynamic/parameterized models can require solver preflight/build inspection before execution.",
      "If executionEligibility is REJECTED, never execute the model. If it is INCOMPLETE, explain the missing structural signals instead of pretending the model is runnable.",
      "Component, variable and module names are hints only and do not prove engineering roles such as girder, tower, bearing, or damper location.",
      "Do not hard-code X/Y/Z as longitudinal/transverse/vertical unless the project or user establishes that convention.",
    ],
    parameters: Type.Object({ path: Type.String({ description: "Workspace-relative FEM model entrypoint path" }) }),
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
    description: "Check installation/configuration and declared capabilities of OpenSeesPy or ANSYS MAPDL without running a finite-element analysis.",
    promptSnippet: "Check concrete solver availability before preflight or execution",
    promptGuidelines: [
      "Use fem_solver_status when solver availability is unknown; fem_health does not prove a solver is installed.",
      "For ANSYS, an unavailable status means FEM_ANSYS_EXECUTABLE is not configured to a valid runtime file; do not guess an installation path.",
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
    description: "Validate solver availability plus model-bundle compatibility without performing the requested solve. OpenSees Python and ANSYS APDL bundles use solver-specific build-only inspection before execution.",
    promptSnippet: "Preflight the concrete FEM solver after static model inspection and before execution",
    promptGuidelines: [
      "Call fem_solver_preflight before fem_solver_run and resolve BLOCKED checks before requesting execution.",
      "For OpenSees Python model bundles, loadPath may be omitted when the model script owns its load and analysis definition.",
      "For the controlled OpenSees ELASTIC_SDOF JSON model, a canonical FEMAGENT_LOAD_CSV_V1 load remains required.",
      "For ANSYS PR8, APDL/CDB model bundles own their analysis/load application. A provided loadPath is provenance only and is not injected into APDL.",
      "ANSYS preflight stages a sanitized build-only bundle and must stop before /SOLU, SOLVE, or postprocessing; inspect BUILD_ONLY_INSPECTION before execution.",
    ],
    parameters: Type.Object({
      solver: solverName,
      modelPath: Type.String({ description: "Workspace-relative solver model entrypoint path" }),
      loadPath: Type.Optional(Type.String({ description: "Optional external load path; solver-specific preflight determines whether it is consumed or provenance-only" })),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemSolverPreflight(ctx.cwd, params.solver, params.modelPath, params.loadPath, signal);
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });

  pi.registerTool({
    name: "fem_solver_run",
    label: "Run FEM Solver",
    description: "Execute a real finite-element solver through its isolated SolverAdapter and return deterministic run provenance. This is an EXECUTION-risk tool and is permission-gated.",
    promptSnippet: "Run a user-approved real FEM analysis only after successful solver preflight",
    promptGuidelines: [
      "Never call fem_solver_run before fem_solver_preflight reports READY.",
      "fem_solver_run is an EXECUTION action. The permission gate must obtain user approval before the solver starts.",
      "OpenSees Python entrypoints may own their load/analysis definition; omitted loadPath is valid only when preflight reports MODEL_SCRIPT_MANAGED.",
      "ANSYS runs must execute the staged Model Bundle, not the user's original source directory; preserve bundleFingerprint and per-file hashes as provenance.",
      "Do not execute a model whose static inspection, dependency graph, or build-only inspection is blocked.",
      "PR8 ANSYS run completion proves the MAPDL process returned successfully and outputs were captured; numerical result truth still requires later Result Intelligence rather than LLM inference.",
    ],
    parameters: Type.Object({
      solver: solverName,
      modelPath: Type.String({ description: "Workspace-relative solver model entrypoint path" }),
      loadPath: Type.Optional(Type.String({ description: "Optional external load path; solver-specific contract determines whether it is consumed or provenance-only" })),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemSolverRun(ctx.cwd, params.solver, params.modelPath, params.loadPath, signal);
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });
}
