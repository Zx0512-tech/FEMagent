import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runFemEngineeringPerformanceEvaluation,
  type FemEngineeringPerformanceRequest,
} from "@femagent/fem-tools";
import { Type } from "typebox";

const metricId = Type.String({ pattern: "^[A-Za-z][A-Za-z0-9_-]{0,63}$" });
const roleId = Type.String({ pattern: "^[A-Z][A-Z0-9_]{0,63}$" });
const constraintId = Type.String({ pattern: "^[A-Za-z][A-Za-z0-9_-]{0,63}$" });

const absolutePeakMetric = Type.Object(
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
      Type.Literal("DAMPER_RESPONSE"),
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
      Type.Literal("FORCE"),
      Type.Literal("DEFORMATION"),
      Type.Literal("VELOCITY"),
      Type.Literal("DISSIPATED_ENERGY"),
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

const relativeDisplacementMetric = Type.Object(
  {
    metricId,
    type: Type.Literal("ROLE_RELATIVE_DISPLACEMENT_PEAK"),
    targetRoleId: roleId,
    referenceRoleId: roleId,
    component: Type.Union([Type.Literal("X"), Type.Literal("Y")]),
  },
  { additionalProperties: false },
);

const reactionResultantMetric = Type.Object(
  {
    metricId,
    type: Type.Literal("ROLE_GROUP_REACTION_RESULTANT_PEAK"),
    roleIds: Type.Array(roleId, { minItems: 1, maxItems: 32 }),
    components: Type.Tuple([Type.Literal("X"), Type.Literal("Y")]),
  },
  { additionalProperties: false },
);

const metricsRequest = Type.Object(
  {
    schema: Type.Literal("FEMAGENT_ENGINEERING_RESPONSE_METRIC_REQUEST_V1"),
    runRef: Type.String({ minLength: 1 }),
    modelPath: Type.String({ minLength: 1 }),
    semanticManifestPath: Type.String({ minLength: 1 }),
    metrics: Type.Array(
      Type.Union([
        absolutePeakMetric,
        relativeDisplacementMetric,
        reactionResultantMetric,
      ]),
      { minItems: 1, maxItems: 50 },
    ),
  },
  { additionalProperties: false },
);

const constraint = Type.Object(
  {
    constraintId,
    metricId,
    operator: Type.Literal("MAXIMUM"),
    limit: Type.Number({ minimum: 0 }),
    unit: Type.String({ minLength: 1 }),
    label: Type.Optional(Type.String({ minLength: 1 })),
  },
  { additionalProperties: false },
);

function toolResult(report: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(report, null, 2) }],
    details: report,
  };
}

export default function performanceConstraintToolsExtension(pi: ExtensionAPI) {
  pi.registerTool({
    name: "fem_performance_evaluate",
    label: "Evaluate FEM Engineering Performance Constraints",
    description:
      "Evaluate explicitly supplied upper-bound engineering constraints against verified PR34 response metrics. SAFE and read-only; never executes a solver or invents design limits.",
    promptSnippet:
      "Compare verified FEM response peaks with explicit project/user limits and report FEASIBLE, INFEASIBLE, or LIMITED without inventing criteria",
    promptGuidelines: [
      "Use only limit values and units explicitly supplied by the user or authoritative project context. Never invent a code limit, allowable displacement, device stroke, or force capacity.",
      "Every constraint must reference a metricId declared inside the same metricsRequest.",
      "PR35 V1 supports operator=MAXIMUM only. SATISFIED means absolutePeak <= explicit limit with no hidden tolerance.",
      "Units must match exactly. There is no unit conversion; N vs kN or m vs mm is NOT_EVALUABLE rather than converted.",
      "Unknown solver-native units, including unproven ANSYS units, are NOT_EVALUABLE for explicit physical constraints.",
      "DAMPER_RESPONSE force/deformation/velocity/dissipated-energy constraints require an explicit ELEMENT semantic role and a response channel already recorded by Result Intelligence.",
      "FEASIBLE means only that every explicit constraint in this request is satisfied. Do not present it as general structural safety or code compliance.",
      "INFEASIBLE means at least one explicit constraint is proven violated. LIMITED means no violation is proven but at least one constraint cannot be evaluated.",
      "The governing constraint is descriptive within this one evaluated constraint set; do not use it to rank competing designs.",
      "This tool never calls fem_solver_run, changes parameters, repairs a model, or performs optimization.",
    ],
    parameters: Type.Object(
      {
        schema: Type.Literal("FEMAGENT_ENGINEERING_PERFORMANCE_REQUEST_V1"),
        metricsRequest,
        constraints: Type.Array(constraint, { minItems: 1, maxItems: 100 }),
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemEngineeringPerformanceEvaluation(
        ctx.cwd,
        params as FemEngineeringPerformanceRequest,
        signal,
      );
      return toolResult(report);
    },
  });
}
