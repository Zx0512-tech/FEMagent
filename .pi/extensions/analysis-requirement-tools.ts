import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runFemAnalysisRequirementComplete,
  type FemEngineeringAnalysisRequirementDraft,
  type FemEngineeringModelSpecInput,
} from "@femagent/fem-tools";
import { Type } from "typebox";

const evidence = Type.Object(
  {
    sourceId: Type.String({ minLength: 1 }),
    quote: Type.String({ minLength: 1 }),
  },
  { additionalProperties: false },
);

const explicitBase = {
  source: Type.Literal("USER_EXPLICIT"),
  evidence,
};

const roleType = Type.Union([
  Type.Literal("GIRDER_END"),
  Type.Literal("TOWER_BASE"),
  Type.Literal("MIDSPAN"),
  Type.Literal("SUPPORT"),
  Type.Literal("BEARING"),
  Type.Literal("DAMPER_ATTACHMENT"),
]);

const resultTarget = Type.Union([
  Type.Object(
    {
      type: Type.Literal("NODE"),
      id: Type.Integer({ minimum: 1 }),
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      type: Type.Literal("SEMANTIC_ROLE_TYPE"),
      roleType,
    },
    { additionalProperties: false },
  ),
]);

const fact = Type.Union([
  Type.Object(
    {
      kind: Type.Literal("EXCITATION_COMPONENT"),
      ...explicitBase,
      component: Type.Union([Type.Literal("X"), Type.Literal("Y")]),
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      kind: Type.Literal("LOAD_SELECTION"),
      ...explicitBase,
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      kind: Type.Literal("DAMPING_NONE"),
      ...explicitBase,
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      kind: Type.Literal("RAYLEIGH_DAMPING"),
      ...explicitBase,
      alphaM: Type.Number({ minimum: 0 }),
      betaK: Type.Number({ minimum: 0 }),
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      kind: Type.Literal("RESULT_REQUEST"),
      ...explicitBase,
      quantity: Type.Union([
        Type.Literal("DISPLACEMENT"),
        Type.Literal("REACTION_FORCE"),
      ]),
      target: resultTarget,
      component: Type.Optional(
        Type.Union([Type.Literal("X"), Type.Literal("Y")]),
      ),
    },
    { additionalProperties: false },
  ),
]);

const draftSchema = Type.Object(
  {
    schema: Type.Literal("FEMAGENT_ANALYSIS_REQUIREMENT_DRAFT_V1"),
    profile: Type.Literal("TRANSIENT_UNIFORM_BASE_REQUIREMENT_V1"),
    sources: Type.Array(
      Type.Object(
        {
          sourceId: Type.String({ minLength: 1 }),
          kind: Type.Literal("USER_MESSAGE"),
          text: Type.String({ minLength: 1 }),
        },
        { additionalProperties: false },
      ),
      { minItems: 1 },
    ),
    intent: Type.Object(
      {
        type: Type.Literal("TRANSIENT_UNIFORM_BASE"),
        evidence,
      },
      { additionalProperties: false },
    ),
    facts: Type.Array(fact),
  },
  { additionalProperties: false },
);

const semanticContext = Type.Object(
  {
    modelPath: Type.String({ minLength: 1 }),
    manifestPath: Type.String({ minLength: 1 }),
  },
  { additionalProperties: false },
);

function toolResult(report: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(report, null, 2) }],
    details: report,
  };
}

export default function analysisRequirementToolsExtension(pi: ExtensionAPI) {
  pi.registerTool({
    name: "fem_analysis_requirement_complete",
    label: "Complete FEM Analysis Requirement",
    description:
      "Deterministically complete an evidence-backed natural-language earthquake time-history requirement into EngineeringAnalysisSpec V2. SAFE and read-only; it never renders or runs a solver.",
    promptSnippet:
      "Turn explicit earthquake-analysis language into a controlled AnalysisSpec requirement draft, then let Python bind model/load/semantic truth",
    promptGuidelines: [
      "Copy USER_MESSAGE source text exactly. Every USER_EXPLICIT fact must cite an evidence.quote that is an exact substring; never fabricate evidence.",
      "V1 supports only TRANSIENT + UNIFORM_BASE_EXCITATION with X/Y acceleration, explicit NONE or explicit Rayleigh alphaM/betaK damping, and NODE DISPLACEMENT/REACTION_FORCE X/Y outputs.",
      "Never assume zero damping. A damping ratio such as 5% is not permission to invent Rayleigh coefficients; report damping as incomplete unless alphaM/betaK are explicit or the user explicitly requests no damping.",
      "Use loadArtifactPath only for a canonical FEMAGENT_LOAD_CSV_V1 artifact already selected/standardized from deterministic load tooling. Python re-reads and hashes it and derives dt/duration; never type dt, duration, or SHA into the draft.",
      "For engineering names such as 梁端 or 塔底, use SEMANTIC_ROLE_TYPE only when a current explicit Semantic Role Manifest is available. Never guess a roleId, NODE id, or role mapping from geometry or names.",
      "If more than one explicit role of the requested type exists, preserve AMBIGUOUS and ask which role is intended.",
      "Do not map 塔底剪力 to one nodal reaction automatically. V1 accepts explicit reaction-force wording only; base shear aggregation/generalized-force semantics require later scope.",
      "COMPLETE means only that a candidate AnalysisSpec V2 passed intrinsic validation. Call analysis readiness before render/preflight/run.",
      "This tool is SAFE/read-only and must never call OpenSees or ANSYS execution.",
    ],
    parameters: Type.Object(
      {
        draft: draftSchema,
        modelSpec: Type.Object({}, { additionalProperties: true }),
        loadArtifactPath: Type.String({
          minLength: 1,
          description:
            "Workspace-relative canonical FEMAGENT_LOAD_CSV_V1 earthquake artifact path",
        }),
        semanticContext: Type.Optional(semanticContext),
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemAnalysisRequirementComplete(
        ctx.cwd,
        params.draft as FemEngineeringAnalysisRequirementDraft,
        params.modelSpec as FemEngineeringModelSpecInput,
        params.loadArtifactPath,
        params.semanticContext,
        signal,
      );
      return toolResult(report);
    },
  });
}
