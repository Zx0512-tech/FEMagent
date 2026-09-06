import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { runFemResultInspect, runFemResultQuery } from "@femagent/fem-tools";
import { Type } from "typebox";

const operation = Type.Union([Type.Literal("SUMMARY"), Type.Literal("SERIES")]);
const paging = {
  operation,
  offset: Type.Optional(Type.Integer({ minimum: 0 })),
  limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 5000 })),
};
const nodeTarget = Type.Object({
  type: Type.Literal("NODE"),
  id: Type.Integer({ minimum: 1 }),
});
const elementTarget = Type.Object({
  type: Type.Literal("ELEMENT"),
  id: Type.Integer({ minimum: 1 }),
});
const structuralTarget = Type.Union([nodeTarget, elementTarget]);
const stressComponent = Type.Union([
  Type.Literal("SX"), Type.Literal("SY"), Type.Literal("SZ"),
  Type.Literal("SXY"), Type.Literal("SYZ"), Type.Literal("SXZ"),
]);
const principalComponent = Type.Union([
  Type.Literal("S1"), Type.Literal("S2"), Type.Literal("S3"),
  Type.Literal("SINT"), Type.Literal("SEQV"),
]);
const generalizedComponent = Type.Union([
  Type.Literal("N"), Type.Literal("VY"), Type.Literal("VZ"),
  Type.Literal("T"), Type.Literal("MY"), Type.Literal("MZ"),
]);
const generalizedLocation = Type.Union([
  Type.Literal("END_I"), Type.Literal("END_J"), Type.Literal("SECTION"),
]);
const damperComponent = Type.Union([
  Type.Literal("FORCE"), Type.Literal("DEFORMATION"), Type.Literal("VELOCITY"),
  Type.Literal("DISSIPATED_ENERGY"),
]);

const structuralQuery = Type.Union([
  Type.Object({
    quantity: Type.Union([
      Type.Literal("DISPLACEMENT"), Type.Literal("VELOCITY"),
      Type.Literal("ACCELERATION"), Type.Literal("REACTION_FORCE"),
      Type.Literal("REACTION_MOMENT"),
    ]),
    target: nodeTarget,
    component: Type.String({ description: "Recorded Cartesian alias such as X or UX; deterministic Python validation is authoritative" }),
    ...paging,
  }),
  Type.Object({
    quantity: Type.Literal("STRESS"),
    target: structuralTarget,
    component: stressComponent,
    ...paging,
  }),
  Type.Object({
    quantity: Type.Literal("PRINCIPAL_STRESS"),
    target: structuralTarget,
    component: principalComponent,
    ...paging,
  }),
  Type.Object({
    quantity: Type.Literal("GENERALIZED_FORCE"),
    target: elementTarget,
    component: generalizedComponent,
    location: generalizedLocation,
    ...paging,
  }),
  Type.Object({
    quantity: Type.Literal("DAMPER_RESPONSE"),
    target: elementTarget,
    component: damperComponent,
    ...paging,
  }),
]);

export default function structuralResponseToolsExtension(pi: ExtensionAPI) {
  pi.registerTool({
    name: "fem_structural_response_inspect",
    label: "Inspect Structural Responses",
    description: "Inspect a completed FEMagent run and enumerate artifact-backed NODE/ELEMENT structural response channels. SAFE and read-only; never executes a solver.",
    promptSnippet: "Inspect recorded structural response capabilities and integrity before querying values",
    promptGuidelines: [
      "Call this before structural response queries and use only channels explicitly advertised by Result Intelligence.",
      "Never invent NODE or ELEMENT IDs. Resolve engineering roles through explicit Semantic Role manifests when the target is described by engineering meaning.",
      "Never infer ANSYS units from magnitudes or defaults; unit:null remains unknown.",
      "Never infer local axes, END_I/END_J meaning, stress averaging, or unavailable solver mappings.",
      "Preserve artifact hash errors and LIMITED states; absence of a channel never means a physical response is zero.",
      "This tool is read-only and must never execute OpenSees or ANSYS.",
    ],
    parameters: Type.Object({
      runRef: Type.String({ description: "Completed FEMagent run reference" }),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemResultInspect(ctx.cwd, params.runRef, signal);
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });

  pi.registerTool({
    name: "fem_structural_response_query",
    label: "Query Structural Response",
    description: "Query one deterministic recorded NODE/ELEMENT structural response channel from a completed FEMagent run. SAFE and read-only; never executes a solver.",
    promptSnippet: "Query only an explicitly recorded structural response identity after inspecting capabilities",
    promptGuidelines: [
      "Use exactly the target, quantity, component, and location advertised or deterministically established by model/semantic evidence.",
      "Do not turn an element-nodal stress matrix into a scalar by averaging or taking a maximum unless Result Intelligence explicitly exposes that operation.",
      "Do not invent generalized-force mappings for unsupported element formulations.",
      "If unit is null, report it as unknown and do not convert it.",
      "For ELEMENT generalized forces, preserve explicit END_I/END_J/SECTION and ELEMENT_LOCAL reference-frame semantics.",
      "This tool reads hashed recorded artifacts only and must never trigger a solve.",
    ],
    parameters: Type.Object({
      runRef: Type.String({ description: "Completed FEMagent run reference" }),
      query: structuralQuery,
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemResultQuery(ctx.cwd, params.runRef, params.query, signal);
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });
}
