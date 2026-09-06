import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runFemEvidenceProject,
  runFemHealth,
  runFemLoadInspect,
  runFemLoadStandardize,
  runFemModelInspect,
  runFemResultInspect,
  runFemResultQuery,
  runFemSolverPreflight,
  runFemSolverRun,
  runFemSolverStatus,
} from "@femagent/fem-tools";
import { Type } from "typebox";

const solverName = Type.Union([Type.Literal("opensees"), Type.Literal("ansys")], {
  description: "Concrete FEM solver adapter. Current support is OpenSeesPy and ANSYS MAPDL.",
});

const ansysModelUnits = Type.Object({
  length: Type.Union([Type.Literal("m"), Type.Literal("cm"), Type.Literal("mm")], {
    description: "Declared ANSYS model length unit. FEMagent never infers this from model magnitudes.",
  }),
  time: Type.Union([Type.Literal("s"), Type.Literal("ms")], {
    description: "Declared ANSYS model time unit. Required with an ANSYS canonical external load.",
  }),
});

const solverOptions = Type.Object({
  modelUnits: Type.Optional(ansysModelUnits),
  responsePlanPath: Type.Optional(Type.String({
    description: "Workspace-relative strict OpenSees Structural Response Plan path. This is a JSON plan path only, never recorder commands or arbitrary arguments.",
  })),
});

const resultQuantity = Type.Union(
  [
    Type.Literal("DISPLACEMENT"),
    Type.Literal("VELOCITY"),
    Type.Literal("ACCELERATION"),
    Type.Literal("REACTION_FORCE"),
  ],
  { description: "Recorded nodal result quantity to query" },
);

const resultOperation = Type.Union([Type.Literal("SUMMARY"), Type.Literal("SERIES")], {
  description: "Return extrema/peak summary or a bounded recorded series slice",
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
    name: "fem_result_inspect",
    label: "Inspect FEM Results",
    description: "Read and validate a completed FEMagent solver run, verify recorded result artifacts and enumerate deterministic query capabilities without rerunning a solver.",
    promptSnippet: "Inspect completed FEM results before making numerical response claims",
    promptGuidelines: [
      "Use fem_result_inspect before making numerical claims from a completed run; inspect integrity.status and warnings first.",
      "VALID means the recorded result artifact passed the available integrity/reader checks. LIMITED means standardized numerical evidence is unavailable or incomplete; it never means the physical response is zero.",
      "For controlled OpenSees response.csv runs, SI units and time seconds are proven by the FEMagent recorder contract.",
      "For ANSYS MAPDL binary results, unit:null means the model unit system is not proven. Never silently label solver-native values as SI.",
      "ANSYS SOLVER_NATIVE_RESULT_ABSCISSA must not be called time in seconds unless separate model/project evidence establishes that interpretation.",
      "Result capabilities do not prove engineering roles such as tower base, girder end or bearing. Resolve engineering role to deterministic node IDs separately; never guess IDs from names.",
      "This tool is read-only and must never trigger solver execution.",
    ],
    parameters: Type.Object({
      runRef: Type.String({ description: "run_<id>, workspace-relative run directory, or run_manifest.json path" }),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemResultInspect(ctx.cwd, params.runRef, signal);
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });

  pi.registerTool({
    name: "fem_result_query",
    label: "Query FEM Results",
    description: "Query one recorded nodal result series or summary from a completed FEMagent run. This is a SAFE read-only operation and never invokes a solver.",
    promptSnippet: "Query deterministic recorded FEM response values after inspecting available result capabilities",
    promptGuidelines: [
      "Call fem_result_inspect first and query only a quantity/component supported by the recorded artifacts.",
      "Never use fem_result_query as a substitute for resolving an unknown engineering target. Node IDs must come from deterministic model/project evidence.",
      "If unit is null, report the unit as unknown rather than inferring SI from magnitude or solver defaults.",
      "Do not interpret solver-native ANSYS abscissa values as seconds unless separate evidence proves the analysis semantics and unit system.",
      "SUMMARY and SERIES are computed from recorded artifacts only; this tool never reruns OpenSees or ANSYS.",
    ],
    parameters: Type.Object({
      runRef: Type.String({ description: "run_<id>, workspace-relative run directory, or run_manifest.json path" }),
      quantity: resultQuantity,
      target: Type.Object({
        type: Type.Literal("NODE"),
        id: Type.Integer({ minimum: 1, description: "Recorded solver node ID" }),
      }),
      component: Type.String({ description: "Cartesian component alias such as X, UX, U1, or 1" }),
      operation: resultOperation,
      offset: Type.Optional(Type.Integer({ minimum: 0, description: "SERIES starting sample offset" })),
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 5000, description: "SERIES maximum returned samples" })),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemResultQuery(
        ctx.cwd,
        params.runRef,
        {
          quantity: params.quantity,
          target: params.target,
          component: params.component,
          operation: params.operation,
          ...(params.offset === undefined ? {} : { offset: params.offset }),
          ...(params.limit === undefined ? {} : { limit: params.limit }),
        },
        signal,
      );
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });

  pi.registerTool({
    name: "fem_evidence_project",
    label: "Project FEM Evidence",
    description: "Project one recorded Result Intelligence query into artifact-backed Engineering Evidence. This is a SAFE read-only operation: it verifies recorded artifact integrity and never invokes a solver.",
    promptSnippet: "Promote a deterministic recorded result into auditable Engineering Evidence only after target identity is known",
    promptGuidelines: [
      "Use fem_evidence_project only for a deterministic run and node target already established by project/model evidence; never guess engineering role-to-node mappings.",
      "The tool verifies recorded result artifacts before promotion. If integrity verification fails, preserve the error rather than inventing or downgrading a claim.",
      "Only VERIFIED evidence may be described as a verified engineering claim. LIMITED, INVALID and UNVERIFIED entries remain limitations.",
      "Do not infer physical units when the returned metric unit is null, especially for solver-native ANSYS results.",
      "This tool is read-only and must never trigger OpenSees or ANSYS execution.",
    ],
    parameters: Type.Object({
      projectId: Type.String({ description: "Caller-defined project identifier used to group projected evidence" }),
      runRef: Type.String({ description: "run_<id>, workspace-relative run directory, or run_manifest.json path" }),
      evidenceId: Type.String({ description: "Stable caller-defined evidence identifier" }),
      quantity: resultQuantity,
      target: Type.Object({
        type: Type.Literal("NODE"),
        id: Type.Integer({ minimum: 1, description: "Deterministically resolved solver node ID" }),
      }),
      component: Type.String({ description: "Cartesian component alias such as X, UX, U1, or 1" }),
      operation: resultOperation,
      offset: Type.Optional(Type.Integer({ minimum: 0, description: "SERIES starting sample offset" })),
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 5000, description: "SERIES maximum returned samples" })),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemEvidenceProject(
        ctx.cwd,
        params.projectId,
        params.runRef,
        params.evidenceId,
        {
          quantity: params.quantity,
          target: params.target,
          component: params.component,
          operation: params.operation,
          ...(params.offset === undefined ? {} : { offset: params.offset }),
          ...(params.limit === undefined ? {} : { limit: params.limit }),
        },
        signal,
      );
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
    description: "Validate solver availability plus model-bundle compatibility without performing the requested solve. ANSYS canonical external loads are build-checked in a staged bundle before execution.",
    promptSnippet: "Preflight the concrete FEM solver after static model/load inspection and before execution",
    promptGuidelines: [
      "Call fem_solver_preflight before fem_solver_run and resolve BLOCKED checks before requesting execution.",
      "For OpenSees Python model bundles, loadPath may be omitted when the model script owns its load and analysis definition.",
      "For OpenSees structural recording, solverOptions.responsePlanPath may point only to FEMagent's strict Structural Response Plan JSON; never pass recorder strings, commands, or arbitrary arguments.",
      "For the controlled OpenSees ELASTIC_SDOF JSON model, a canonical FEMAGENT_LOAD_CSV_V1 load remains required.",
      "OpenSees does not accept ANSYS solverOptions.modelUnits and must fail closed when they are supplied.",
      "For ANSYS with loadPath, declare solverOptions.modelUnits.length and .time from deterministic project/user evidence; never guess model units.",
      "ANSYS PR10 accepts one FEMAGENT_LOAD_CSV_V1 EARTHQUAKE + UNIFORM_EXCITATION + ACCELERATION channel and validates the transient injection hook before execution.",
      "ANSYS preflight stages a sanitized build-only bundle, validates generated load artifacts, and must not advance the requested solve.",
    ],
    parameters: Type.Object({
      solver: solverName,
      modelPath: Type.String({ description: "Workspace-relative solver model entrypoint path" }),
      loadPath: Type.Optional(Type.String({ description: "Optional canonical external load path; ANSYS PR10 consumes the supported canonical earthquake contract" })),
      solverOptions: Type.Optional(solverOptions),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemSolverPreflight(
        ctx.cwd,
        params.solver,
        params.modelPath,
        params.loadPath,
        params.solverOptions,
        signal,
      );
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
      "For OpenSees structural recording, pass exactly the same strict solverOptions.responsePlanPath used for READY preflight; do not synthesize recorder commands or mutate the plan between preflight and run.",
      "For ANSYS canonical injection, pass the same loadPath and solverOptions.modelUnits that produced READY preflight; do not alter or infer them between preflight and run.",
      "ANSYS runs must generate load artifacts and inject only into the staged Model Bundle, never the user's source model; inspect load/injection hashes and executionInputFingerprint in the run manifest.",
      "Do not execute a model whose static inspection, dependency graph, canonical-load injection check, structural response mapping check, or build-only inspection is blocked.",
      "ANSYS run completion proves the MAPDL process returned successfully and outputs were captured; use fem_result_inspect/query for numerical result truth rather than LLM inference.",
    ],
    parameters: Type.Object({
      solver: solverName,
      modelPath: Type.String({ description: "Workspace-relative solver model entrypoint path" }),
      loadPath: Type.Optional(Type.String({ description: "Optional canonical external load path; solver-specific contract determines whether it is consumed" })),
      solverOptions: Type.Optional(solverOptions),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemSolverRun(
        ctx.cwd,
        params.solver,
        params.modelPath,
        params.loadPath,
        params.solverOptions,
        signal,
      );
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });
}
