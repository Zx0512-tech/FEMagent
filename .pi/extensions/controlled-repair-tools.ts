import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runFemControlledRepairPlan,
  runFemControlledRepairRetry,
  type FemControlledRepairResolution,
  type FemEarthquakeWorkflowPreparation,
  type FemEarthquakeWorkflowPrepareInput,
} from "@femagent/fem-tools";
import { Type } from "typebox";

function toolResult(report: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(report, null, 2) }],
    details: report,
  };
}

export default function controlledRepairToolsExtension(pi: ExtensionAPI) {
  pi.registerTool({
    name: "fem_controlled_repair_plan",
    label: "Plan FEM Controlled Repair",
    description:
      "Diagnose a blocked earthquake workflow and return only fail-closed, typed repair actions. SAFE/read-only; never edits source files or runs a solver.",
    promptSnippet:
      "Diagnose why earthquake workflow preparation is blocked and present only controlled repair options",
    promptGuidelines: [
      "Use only after fem_earthquake_workflow_prepare returns NEEDS_INPUT, ANALYSIS_NOT_READY, or PREFLIGHT_BLOCKED.",
      "Do not invent engineering values. Missing mass, constraints, damping, semantic targets, or solver configuration remain explicit repair actions.",
      "USER_INPUT actions may be retried only after the user explicitly supplies/approves the requested value or choice.",
      "MANUAL_ENGINEERING_CHANGE actions are not auto-fixed. Ask for a revised ModelSpec/requirement/context as appropriate.",
      "OPERATOR_ACTION means restore/configure the solver/runtime or inspect diagnostics; do not mutate the engineering model to make preflight pass.",
      "This tool never calls fem_solver_run.",
    ],
    parameters: Type.Object(
      {
        workflowInput: Type.Record(Type.String(), Type.Unknown()),
        failedPreparation: Type.Record(Type.String(), Type.Unknown()),
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemControlledRepairPlan(
        ctx.cwd,
        params.workflowInput as unknown as FemEarthquakeWorkflowPrepareInput,
        params.failedPreparation as unknown as FemEarthquakeWorkflowPreparation,
        signal,
      );
      return toolResult(report);
    },
  });

  pi.registerTool({
    name: "fem_controlled_repair_retry",
    label: "Retry FEM Controlled Repair",
    description:
      "Apply only user-confirmed typed repair resolutions to workflow input, then rerun deterministic earthquake preparation. SAFE: never executes the real solver.",
    promptSnippet:
      "Apply explicit repair resolutions and rerun workflow preparation without bypassing engineering or execution gates",
    promptGuidelines: [
      "Use the exact planFingerprint returned by fem_controlled_repair_plan. A stale/tampered plan must fail closed.",
      "Only submit resolutions the user has explicitly confirmed or supplied. Do not choose NONE damping, Rayleigh coefficients, X/Y directions, model mass, constraints, load files, or ANSYS model paths yourself.",
      "Evidence-backed resolutions require sourceText and quote copied exactly from the user's new message; Python sends the patched draft back through PR30 evidence validation.",
      "REPLACE_MODEL_SPEC requires a complete revised ModelSpec; never synthesize missing mass or constraints.",
      "If retry remains blocked, diagnose the new preparation rather than forcing execution.",
      "If retry becomes READY_FOR_CONFIRMATION, real execution still goes through the existing permission-gated fem_solver_run.",
      "This tool never calls fem_solver_run.",
    ],
    parameters: Type.Object(
      {
        workflowInput: Type.Record(Type.String(), Type.Unknown()),
        failedPreparation: Type.Record(Type.String(), Type.Unknown()),
        planFingerprint: Type.String({ pattern: "^[0-9a-f]{64}$" }),
        resolutions: Type.Array(Type.Record(Type.String(), Type.Unknown())),
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemControlledRepairRetry(
        ctx.cwd,
        params.workflowInput as unknown as FemEarthquakeWorkflowPrepareInput,
        params.failedPreparation as unknown as FemEarthquakeWorkflowPreparation,
        params.planFingerprint,
        params.resolutions as unknown as FemControlledRepairResolution[],
        signal,
      );
      return toolResult(report);
    },
  });
}
