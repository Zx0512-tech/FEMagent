import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runFemRequirementComplete,
  type FemEngineeringRequirementDraft,
} from "@femagent/fem-tools";
import { Type } from "typebox";

const positiveId = Type.Integer({ minimum: 1 });
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
const lengthUnit = Type.Union([
  Type.Literal("m"),
  Type.Literal("cm"),
  Type.Literal("mm"),
]);
const dof = Type.Union([
  Type.Literal("UX"),
  Type.Literal("UY"),
  Type.Literal("RZ"),
]);

const fact = Type.Union([
  Type.Object(
    {
      kind: Type.Literal("SPAN"),
      ...explicitBase,
      value: Type.Number({ exclusiveMinimum: 0 }),
      unit: lengthUnit,
    },
    { additionalProperties: false },
  ),
  Type.Union([
    Type.Object(
      {
        kind: Type.Literal("UNIT_DECLARATION"),
        ...explicitBase,
        dimension: Type.Literal("length"),
        value: lengthUnit,
      },
      { additionalProperties: false },
    ),
    Type.Object(
      {
        kind: Type.Literal("UNIT_DECLARATION"),
        ...explicitBase,
        dimension: Type.Literal("force"),
        value: Type.Union([Type.Literal("N"), Type.Literal("kN")]),
      },
      { additionalProperties: false },
    ),
    Type.Object(
      {
        kind: Type.Literal("UNIT_DECLARATION"),
        ...explicitBase,
        dimension: Type.Literal("time"),
        value: Type.Union([Type.Literal("s"), Type.Literal("ms")]),
      },
      { additionalProperties: false },
    ),
  ]),
  Type.Object(
    {
      kind: Type.Literal("YOUNGS_MODULUS"),
      ...explicitBase,
      value: Type.Number({ exclusiveMinimum: 0 }),
      unit: Type.Union([
        Type.Literal("Pa"),
        Type.Literal("N/m²"),
        Type.Literal("N/cm²"),
        Type.Literal("N/mm²"),
        Type.Literal("kN/m²"),
        Type.Literal("kN/cm²"),
        Type.Literal("kN/mm²"),
      ]),
      materialId: Type.Optional(positiveId),
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      kind: Type.Literal("SECTION_AREA"),
      ...explicitBase,
      value: Type.Number({ exclusiveMinimum: 0 }),
      unit: Type.Union([
        Type.Literal("m²"),
        Type.Literal("cm²"),
        Type.Literal("mm²"),
      ]),
      sectionId: Type.Optional(positiveId),
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      kind: Type.Literal("SECTION_IZ"),
      ...explicitBase,
      value: Type.Number({ exclusiveMinimum: 0 }),
      unit: Type.Union([
        Type.Literal("m⁴"),
        Type.Literal("cm⁴"),
        Type.Literal("mm⁴"),
      ]),
      sectionId: Type.Optional(positiveId),
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      kind: Type.Literal("NODE_COORDINATE"),
      ...explicitBase,
      nodeId: positiveId,
      x: Type.Number(),
      y: Type.Number(),
      unit: lengthUnit,
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      kind: Type.Literal("ELEMENT_CONNECTIVITY"),
      ...explicitBase,
      elementId: positiveId,
      nodeI: positiveId,
      nodeJ: positiveId,
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      kind: Type.Literal("ELEMENT_MATERIAL_REF"),
      ...explicitBase,
      elementId: positiveId,
      materialId: positiveId,
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      kind: Type.Literal("ELEMENT_SECTION_REF"),
      ...explicitBase,
      elementId: positiveId,
      sectionId: positiveId,
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      kind: Type.Literal("NODE_CONSTRAINT"),
      ...explicitBase,
      nodeId: positiveId,
      dofs: Type.Array(dof, { minItems: 1, uniqueItems: true }),
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      kind: Type.Literal("NODAL_MASS"),
      ...explicitBase,
      nodeId: positiveId,
      mUX: Type.Number({ minimum: 0 }),
      mUY: Type.Number({ minimum: 0 }),
    },
    { additionalProperties: false },
  ),
]);

const templateId = Type.Union([
  Type.Literal("SIMPLY_SUPPORTED_BEAM_2D_V1"),
  Type.Literal("CANTILEVER_BEAM_2D_V1"),
  Type.Literal("FIXED_FIXED_BEAM_2D_V1"),
]);

const requirementDraftSchema = Type.Object(
  {
    schema: Type.Literal("FEMAGENT_ENGINEERING_REQUIREMENT_DRAFT_V1"),
    profile: Type.Literal("FRAME_2D_REQUIREMENT_V1"),
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
    templateIntent: Type.Union([
      Type.Null(),
      Type.Object(
        {
          templateId,
          evidence,
        },
        { additionalProperties: false },
      ),
    ]),
    facts: Type.Array(fact),
  },
  { additionalProperties: false },
);

function toolResult(report: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(report, null, 2) }],
    details: report,
  };
}

export default function requirementToolsExtension(pi: ExtensionAPI) {
  pi.registerTool({
    name: "fem_requirement_complete",
    label: "Complete FEM Engineering Requirement",
    description:
      "Deterministically evaluate an evidence-backed FRAME_2D requirement draft and, only when all required engineering facts are controlled and consistent, return a candidate EngineeringModelSpec. SAFE and read-only.",
    promptSnippet:
      "Convert explicit user engineering facts into a controlled requirement draft before ModelSpec validation",
    promptGuidelines: [
      "Copy USER_MESSAGE source text exactly and attach evidence.quote as an exact substring for every USER_EXPLICIT fact; never fabricate evidence.",
      "Only facts explicitly stated by the user/project may use source=USER_EXPLICIT. Retrieved knowledge, convention, plausible defaults, and model guesses must not be relabeled as explicit truth.",
      "Do not invent Young's modulus, section area, Iz, force/time units, supports, masses, topology, or identifiers merely to make the requirement COMPLETE.",
      "Use only the versioned controlled template IDs when exact supported template wording is evidenced. Broad or approximate structural labels are not permission to select a template.",
      "Report missing, ambiguous, conflict, and invalid-draft findings exactly. Ask for the missing engineering facts rather than silently filling them.",
      "COMPLETE means only that the deterministic completion contract produced a PR21 candidate. It does not mean PR22 READY, a model is rendered, or any solver domain/analysis has succeeded.",
      "After COMPLETE, call fem_model_spec_validate and fem_model_spec_readiness on the returned candidate before any renderer action. READY remains a separate deterministic gate.",
      "This tool is read-only: it does not write artifacts, select an output path, run a renderer, or execute OpenSees/ANSYS.",
    ],
    parameters: Type.Object(
      { draft: requirementDraftSchema },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemRequirementComplete(
        ctx.cwd,
        params.draft as FemEngineeringRequirementDraft,
        signal,
      );
      return toolResult(report);
    },
  });
}
