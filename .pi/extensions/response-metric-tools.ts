import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runFemEngineeringResponseMetrics,
  type FemEngineeringResponseMetricsRequest,
} from "@femagent/fem-tools";
import { Type } from "typebox";

const metricId = Type.String({ pattern: "^[A-Za-z][A-Za-z0-9_-]{0,63}$" });
const roleId = Type.String({ pattern: "^[A-Z][A-Z0-9_]{0,63}$" });

const roleAbsolutePeak = Type.Object(
  {
    metricId,
    type: Type.Literal("ROLE_ABSOLUTE_PEAK"),
    roleId,
    quantity: Type.Union([
      Type.Literal("DISPLACEMENT"),
      Type.Literal("VELOCITY"),
      Type.Literal("ACCELERATION"),
      Type.Literal("RELATIVE_ACCELERATION"),
      Type.Literal("REACTION_FORCE"),
      Type.Literal("REACTION_MOMENT"),
      Type.Literal("GENERALIZED_FORCE"),
    ]),
    component: Type.Union([
      Type.Literal("X"),
      Type.Literal("Y"),
      Type.Literal("Z"),
      Type.Literal("N"),
      Type.Literal("VY"),
      Type.Literal("VZ"),
      Type.Literal("T"),
      Type.Literal("MY"),
      Type.Literal("MZ"),
    ]),
    location: Type.Optional(
      Type.Union([
        Type.Literal("END_I"),
        Type.Literal("END_J"),
        Type.Literal("SECTION"),
      ]),
    ),
  },
  { additionalProperties: false },
);

const relativeDisplacementPeak = Type.Object(
  {
    metricId,
    type: Type.Literal("ROLE_RELATIVE_DISPLACEMENT_PEAK"),
    targetRoleId: roleId,
    referenceRoleId: roleId,
    component: Type.Union([Type.Literal("X"), Type.Literal("Y")]),
  },
  { additionalProperties: false },
);

const groupReactionResultantPeak = Type.Object(
  {
    metricId,
    type: Type.Literal("ROLE_GROUP_REACTION_RESULTANT_PEAK"),
    roleIds: Type.Array(roleId, { minItems: 1, maxItems: 32 }),
    components: Type.Tuple([Type.Literal("X"), Type.Literal("Y")]),
  },
  { additionalProperties: false },
);

function toolResult(report: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(report, null, 2) }],
    details: report,
  };
}

export default function responseMetricToolsExtension(pi: ExtensionAPI) {
  pi.registerTool({
    name: "fem_response_metrics_compute",
    label: "Compute FEM Engineering Response Metrics",
    description:
      "Compute deterministic role-backed engineering response metrics from a completed FEMagent run. SAFE and read-only; never executes a solver.",
    promptSnippet:
      "Turn verified solver response channels into explicit engineering metrics without guessing roles, units, axes, or acceptance criteria",
    promptGuidelines: [
      "Use this only after a completed run exists and an explicit Engineering Semantic Role Manifest is bound to the same Model Bundle.",
      "Never invent roleId values. Inspect or resolve the semantic manifest first when role IDs are unknown.",
      "ROLE_ABSOLUTE_PEAK supports NODE displacement/velocity/acceleration/reaction channels and recorded ELEMENT generalized force with explicit location.",
      "Use ROLE_RELATIVE_DISPLACEMENT_PEAK only for two distinct explicit NODE roles. The calculation is target minus reference on exactly aligned samples; the tool never interpolates or resamples.",
      "Use ROLE_GROUP_REACTION_RESULTANT_PEAK for one or more explicit NODE roles when the requested engineering quantity is the simultaneous X/Y reaction vector resultant. Its aggregation is SIGNED_COMPONENT_SUM_THEN_VECTOR_MAGNITUDE: sum signed X/Y components first, then take the vector magnitude.",
      "Unknown ANSYS units remain null. Never relabel or convert them.",
      "A LIMITED report means one or more requested metrics could not be computed from recorded evidence. Never substitute zero or another response channel.",
      "Metrics are numerical response summaries only. Do not turn them into code-compliance or engineering PASS/FAIL judgments without a separate explicit acceptance contract.",
      "This tool never calls fem_solver_run.",
    ],
    parameters: Type.Object(
      {
        schema: Type.Literal("FEMAGENT_ENGINEERING_RESPONSE_METRIC_REQUEST_V1"),
        runRef: Type.String({ minLength: 1 }),
        modelPath: Type.String({ minLength: 1 }),
        semanticManifestPath: Type.String({ minLength: 1 }),
        metrics: Type.Array(
          Type.Union([
            roleAbsolutePeak,
            relativeDisplacementPeak,
            groupReactionResultantPeak,
          ]),
          { minItems: 1, maxItems: 50 },
        ),
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemEngineeringResponseMetrics(
        ctx.cwd,
        params as FemEngineeringResponseMetricsRequest,
        signal,
      );
      return toolResult(report);
    },
  });
}
