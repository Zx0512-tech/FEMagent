import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runFemAnalysisSpecValidate,
  type FemEngineeringAnalysisSpecInput,
} from "@femagent/fem-tools";
import { Type } from "typebox";

const positiveId = Type.Integer({ minimum: 1 });
const idToken = Type.String({ pattern: "^[A-Za-z][A-Za-z0-9_-]{0,63}$" });
const modelSpecFingerprint = Type.String({ pattern: "^[0-9a-f]{64}$" });

const targetNode = Type.Object(
  {
    type: Type.Literal("NODE"),
    id: positiveId,
  },
  { additionalProperties: false },
);

const targetElement = Type.Object(
  {
    type: Type.Literal("ELEMENT"),
    id: positiveId,
  },
  { additionalProperties: false },
);

const resultRequestBase = {
  requestId: idToken,
  loadCaseId: idToken,
};

const resultRequest = Type.Union([
  Type.Object(
    {
      ...resultRequestBase,
      quantity: Type.Literal("DISPLACEMENT"),
      target: targetNode,
      component: Type.Union([Type.Literal("X"), Type.Literal("Y")]),
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      ...resultRequestBase,
      quantity: Type.Literal("REACTION_FORCE"),
      target: targetNode,
      component: Type.Union([Type.Literal("X"), Type.Literal("Y")]),
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      ...resultRequestBase,
      quantity: Type.Literal("REACTION_MOMENT"),
      target: targetNode,
      component: Type.Literal("Z"),
    },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      ...resultRequestBase,
      quantity: Type.Literal("GENERALIZED_FORCE"),
      target: targetElement,
      component: Type.Union([
        Type.Literal("N"),
        Type.Literal("VY"),
        Type.Literal("MZ"),
      ]),
      location: Type.Union([Type.Literal("END_I"), Type.Literal("END_J")]),
    },
    { additionalProperties: false },
  ),
]);

const analysisSpecSchema = Type.Object(
  {
    schemaVersion: Type.Literal("1.0"),
    kind: Type.Literal("engineering_analysis_spec"),
    modelSpecFingerprint,
    analysisType: Type.Literal("LINEAR_STATIC"),
    units: Type.Object(
      {
        force: Type.Union([Type.Literal("N"), Type.Literal("kN")]),
      },
      { additionalProperties: false },
    ),
    loadCases: Type.Array(
      Type.Object(
        {
          loadCaseId: idToken,
          nodalLoads: Type.Array(
            Type.Object(
              {
                nodeId: positiveId,
                FX: Type.Number(),
                FY: Type.Number(),
                MZ: Type.Number(),
              },
              { additionalProperties: false },
            ),
            { minItems: 1 },
          ),
        },
        { additionalProperties: false },
      ),
      { minItems: 1, maxItems: 1 },
    ),
    resultRequests: Type.Array(resultRequest, { minItems: 1 }),
  },
  { additionalProperties: false },
);

function toolResult(report: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(report, null, 2) }],
    details: report,
  };
}

export default function analysisSpecToolsExtension(pi: ExtensionAPI) {
  pi.registerTool({
    name: "fem_analysis_spec_validate",
    label: "Validate FEM Analysis Specification",
    description:
      "Validate a solver-neutral EngineeringAnalysisSpec V1 through the authoritative Python FEM core. SAFE and read-only; it does not render artifacts, execute a solver, or modify the bound model.",
    promptSnippet:
      "Validate explicit linear-static load cases and result requests separately from EngineeringModelSpec",
    promptGuidelines: [
      "Use this tool only for the V1 solver-neutral LINEAR_STATIC AnalysisSpec contract. Model geometry, materials, sections, constraints, and masses belong in EngineeringModelSpec instead.",
      "Do not invent load magnitudes, load directions, target node IDs, result targets, result components, force units, or modelSpecFingerprint values merely to make an AnalysisSpec VALID.",
      "Every nodal load is explicit FX/FY/MZ. Missing components are not implicit zero, duplicate target loads are not automatically summed, and this tool performs no unit conversion or sign inference.",
      "VALID means only that the AnalysisSpec is intrinsically valid and deterministically normalized. It does not prove that referenced nodes/elements exist in the bound ModelSpec or that the analysis is ready to render or solve.",
      "Cross-model existence, fingerprint binding, model readiness, and unit compatibility belong to the later Analysis Readiness gate, not this validator.",
      "Result requests are limited to the V1 whitelist: node displacement X/Y, node reaction force X/Y, node reaction moment Z, and element generalized force N/VY/MZ at END_I or END_J.",
      "This tool is read-only: it never writes OpenSees/APDL files, applies loads to a solver model, calls solver preflight/run, or repairs an analysis specification.",
    ],
    parameters: Type.Object(
      { spec: analysisSpecSchema },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemAnalysisSpecValidate(
        ctx.cwd,
        params.spec as FemEngineeringAnalysisSpecInput,
        signal,
      );
      return toolResult(report);
    },
  });
}
