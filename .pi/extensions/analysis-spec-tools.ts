import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runFemAnalysisReadiness,
  runFemAnalysisRenderOpenSees,
  runFemAnalysisSpecValidate,
  type FemEngineeringAnalysisSpecInput,
  type FemEngineeringModelSpecInput,
} from "@femagent/fem-tools";
import { Type } from "typebox";

const positiveId = Type.Integer({ minimum: 1 });
const idToken = Type.String({ pattern: "^[A-Za-z][A-Za-z0-9_-]{0,63}$" });
const modelSpecFingerprint = Type.String({ pattern: "^[0-9a-f]{64}$" });
const dof = Type.Union([
  Type.Literal("UX"),
  Type.Literal("UY"),
  Type.Literal("RZ"),
]);

const modelSpecSchema = Type.Object(
  {
    schemaVersion: Type.Literal("1.0"),
    kind: Type.Literal("engineering_model_spec"),
    dimension: Type.Literal("2D"),
    family: Type.Literal("FRAME"),
    coordinateSystem: Type.Literal("CARTESIAN_XY"),
    units: Type.Object(
      {
        length: Type.Union([Type.Literal("m"), Type.Literal("cm"), Type.Literal("mm")]),
        force: Type.Union([Type.Literal("N"), Type.Literal("kN")]),
        time: Type.Union([Type.Literal("s"), Type.Literal("ms")]),
      },
      { additionalProperties: false },
    ),
    nodes: Type.Array(
      Type.Object(
        {
          id: positiveId,
          x: Type.Number(),
          y: Type.Number(),
        },
        { additionalProperties: false },
      ),
      { minItems: 2 },
    ),
    materials: Type.Array(
      Type.Object(
        {
          id: positiveId,
          type: Type.Literal("LINEAR_ELASTIC"),
          youngsModulus: Type.Number(),
        },
        { additionalProperties: false },
      ),
      { minItems: 1 },
    ),
    sections: Type.Array(
      Type.Object(
        {
          id: positiveId,
          type: Type.Literal("FRAME_2D"),
          area: Type.Number(),
          iz: Type.Number(),
        },
        { additionalProperties: false },
      ),
      { minItems: 1 },
    ),
    elements: Type.Array(
      Type.Object(
        {
          id: positiveId,
          type: Type.Literal("ELASTIC_FRAME_2D"),
          formulation: Type.Literal("EULER_BERNOULLI"),
          nodeI: positiveId,
          nodeJ: positiveId,
          materialId: positiveId,
          sectionId: positiveId,
        },
        { additionalProperties: false },
      ),
      { minItems: 1 },
    ),
    constraints: Type.Array(
      Type.Object(
        {
          nodeId: positiveId,
          dofs: Type.Array(dof, { minItems: 1 }),
        },
        { additionalProperties: false },
      ),
    ),
    nodalMasses: Type.Array(
      Type.Object(
        {
          nodeId: positiveId,
          mUX: Type.Number(),
          mUY: Type.Number(),
        },
        { additionalProperties: false },
      ),
    ),
  },
  { additionalProperties: false },
);

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
      "Cross-model existence, fingerprint binding, model readiness, and unit compatibility belong to Analysis Readiness, not intrinsic validation.",
      "Result requests are limited to the V1 whitelist: node displacement X/Y, node reaction force X/Y, node reaction moment Z, and element generalized force N/VY/MZ at END_I or END_J.",
      "This tool is read-only: it never writes OpenSees/APDL files, applies loads to a solver model, calls solver preflight/run, or repairs an analysis specification.",
      "This fine-grained validation tool is temporary. The long-term Agent tool surface should converge into high-level Analysis capabilities instead of multiplying permanent internal validation tools.",
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

  pi.registerTool({
    name: "fem_analysis_prepare_opensees",
    label: "Prepare OpenSees Analysis",
    description:
      "Check or render a bound EngineeringModelSpec + EngineeringAnalysisSpec V1 through one high-level OpenSees analysis preparation capability. CHECK is read-only. RENDER writes only controlled artifacts. Neither runs a solver.",
    promptSnippet:
      "Check joint analysis readiness or render a deterministic OpenSees linear-static analysis bundle without executing it",
    promptGuidelines: [
      "CHECK is read-only and reruns authoritative ModelSpec validation, AnalysisSpec validation, Model Readiness, model fingerprint binding, unit compatibility, target existence, reaction restraint semantics, and proven OpenSees response mapping.",
      "RENDER writes only controlled artifacts below FEMagent's generated-analysis directory after the same readiness gate passes; callers cannot choose an artifact destination.",
      "Neither runs a solver. READY is not execution success, and RENDERED is not execution success; solver preflight and run remain separate controlled capabilities.",
      "Do not mutate engineering facts to force readiness. Never invent or alter supports, topology, node or element IDs, units, loads, result targets, or fingerprints just to make CHECK or RENDER pass.",
      "A NOT_READY or BLOCKED result is a deterministic engineering finding. Report the issue codes and preserve the submitted engineering facts rather than silently repairing them.",
      "V1 remains limited to bound 2D elastic-frame LINEAR_STATIC analysis with one explicit nodal-load case and the approved controlled result-request whitelist.",
    ],
    parameters: Type.Object(
      {
        mode: Type.Union([Type.Literal("CHECK"), Type.Literal("RENDER")]),
        modelSpec: modelSpecSchema,
        analysisSpec: analysisSpecSchema,
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const modelSpec = params.modelSpec as FemEngineeringModelSpecInput;
      const analysisSpec = params.analysisSpec as FemEngineeringAnalysisSpecInput;
      const report = params.mode === "CHECK"
        ? await runFemAnalysisReadiness(ctx.cwd, modelSpec, analysisSpec, signal)
        : await runFemAnalysisRenderOpenSees(ctx.cwd, modelSpec, analysisSpec, signal);
      return toolResult(report);
    },
  });
}
