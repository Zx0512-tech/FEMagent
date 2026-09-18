import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runFemAnalysisReadiness,
  runFemAnalysisRenderOpenSees,
  runFemAnalysisSpecValidate,
  type FemEngineeringAnalysisSpecInput,
  type FemEngineeringAnalysisSpecV1Input,
  type FemEngineeringModelSpecInput,
} from "@femagent/fem-tools";
import { Type } from "typebox";

const positiveId = Type.Integer({ minimum: 1 });
const idToken = Type.String({ pattern: "^[A-Za-z][A-Za-z0-9_-]{0,63}$" });
const modelSpecFingerprint = Type.String({ pattern: "^[0-9a-f]{64}$" });
const sha256 = Type.String({ pattern: "^[0-9a-f]{64}$" });
const forceUnit = Type.Union([Type.Literal("N"), Type.Literal("kN")]);
const xyComponent = Type.Union([Type.Literal("X"), Type.Literal("Y")]);
const generalizedComponent = Type.Union([
  Type.Literal("N"),
  Type.Literal("VY"),
  Type.Literal("MZ"),
]);
const endLocation = Type.Union([Type.Literal("END_I"), Type.Literal("END_J")]);
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
        force: forceUnit,
        time: Type.Union([Type.Literal("s"), Type.Literal("ms")]),
      },
      { additionalProperties: false },
    ),
    nodes: Type.Array(
      Type.Object(
        { id: positiveId, x: Type.Number(), y: Type.Number() },
        { additionalProperties: false },
      ),
      { minItems: 2 },
    ),
    materials: Type.Array(
      Type.Object(
        { id: positiveId, type: Type.Literal("LINEAR_ELASTIC"), youngsModulus: Type.Number() },
        { additionalProperties: false },
      ),
      { minItems: 1 },
    ),
    sections: Type.Array(
      Type.Object(
        { id: positiveId, type: Type.Literal("FRAME_2D"), area: Type.Number(), iz: Type.Number() },
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
        { nodeId: positiveId, dofs: Type.Array(dof, { minItems: 1 }) },
        { additionalProperties: false },
      ),
    ),
    nodalMasses: Type.Array(
      Type.Object(
        { nodeId: positiveId, mUX: Type.Number(), mUY: Type.Number() },
        { additionalProperties: false },
      ),
    ),
  },
  { additionalProperties: false },
);

const targetNode = Type.Object(
  { type: Type.Literal("NODE"), id: positiveId },
  { additionalProperties: false },
);
const targetElement = Type.Object(
  { type: Type.Literal("ELEMENT"), id: positiveId },
  { additionalProperties: false },
);

const v1ResultRequestBase = { requestId: idToken, loadCaseId: idToken };
const v1ResultRequest = Type.Union([
  Type.Object(
    { ...v1ResultRequestBase, quantity: Type.Literal("DISPLACEMENT"), target: targetNode, component: xyComponent },
    { additionalProperties: false },
  ),
  Type.Object(
    { ...v1ResultRequestBase, quantity: Type.Literal("REACTION_FORCE"), target: targetNode, component: xyComponent },
    { additionalProperties: false },
  ),
  Type.Object(
    { ...v1ResultRequestBase, quantity: Type.Literal("REACTION_MOMENT"), target: targetNode, component: Type.Literal("Z") },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      ...v1ResultRequestBase,
      quantity: Type.Literal("GENERALIZED_FORCE"),
      target: targetElement,
      component: generalizedComponent,
      location: endLocation,
    },
    { additionalProperties: false },
  ),
]);

const nodalLoad = Type.Object(
  { nodeId: positiveId, FX: Type.Number(), FY: Type.Number(), MZ: Type.Number() },
  { additionalProperties: false },
);
const loadCase = Type.Object(
  { loadCaseId: idToken, nodalLoads: Type.Array(nodalLoad, { minItems: 1 }) },
  { additionalProperties: false },
);
const singleLoadCases = Type.Array(loadCase, { minItems: 1, maxItems: 1 });
const forceUnits = Type.Object({ force: forceUnit }, { additionalProperties: false });
const emptyUnits = Type.Object({}, { additionalProperties: false });

const analysisSpecV1Schema = Type.Object(
  {
    schemaVersion: Type.Literal("1.0"),
    kind: Type.Literal("engineering_analysis_spec"),
    modelSpecFingerprint,
    analysisType: Type.Literal("LINEAR_STATIC"),
    units: forceUnits,
    loadCases: singleLoadCases,
    resultRequests: Type.Array(v1ResultRequest, { minItems: 1 }),
  },
  { additionalProperties: false },
);

const analysisSpecV2StaticSchema = Type.Object(
  {
    schemaVersion: Type.Literal("2.0"),
    kind: Type.Literal("engineering_analysis_spec"),
    modelSpecFingerprint,
    analysisType: Type.Literal("LINEAR_STATIC"),
    units: forceUnits,
    definition: Type.Object({ loadCases: singleLoadCases }, { additionalProperties: false }),
    resultRequests: Type.Array(v1ResultRequest, { minItems: 1 }),
  },
  { additionalProperties: false },
);

const modalScalarRequest = Type.Object(
  {
    requestId: idToken,
    quantity: Type.Union([
      Type.Literal("EIGENVALUE"),
      Type.Literal("NATURAL_FREQUENCY"),
      Type.Literal("PERIOD"),
    ]),
    mode: positiveId,
  },
  { additionalProperties: false },
);
const modalModeShapeRequest = Type.Object(
  {
    requestId: idToken,
    quantity: Type.Literal("MODE_SHAPE"),
    mode: positiveId,
    target: targetNode,
    component: Type.Union([Type.Literal("X"), Type.Literal("Y"), Type.Literal("RZ")]),
  },
  { additionalProperties: false },
);
const analysisSpecV2ModalSchema = Type.Object(
  {
    schemaVersion: Type.Literal("2.0"),
    kind: Type.Literal("engineering_analysis_spec"),
    modelSpecFingerprint,
    analysisType: Type.Literal("MODAL"),
    units: emptyUnits,
    definition: Type.Object({ modeCount: positiveId }, { additionalProperties: false }),
    resultRequests: Type.Array(Type.Union([modalScalarRequest, modalModeShapeRequest]), { minItems: 1 }),
  },
  { additionalProperties: false },
);

const loadArtifact = Type.Object(
  { path: Type.String({ minLength: 1 }), sha256 },
  { additionalProperties: false },
);
const transientTime = Type.Object(
  { timeStep: Type.Number({ exclusiveMinimum: 0 }), duration: Type.Number({ exclusiveMinimum: 0 }) },
  { additionalProperties: false },
);
const transientDamping = Type.Union([
  Type.Object({ type: Type.Literal("NONE") }, { additionalProperties: false }),
  Type.Object(
    {
      type: Type.Literal("RAYLEIGH"),
      alphaM: Type.Number({ minimum: 0 }),
      betaK: Type.Number({ minimum: 0 }),
    },
    { additionalProperties: false },
  ),
]);
const transientCommonResultRequest = Type.Union([
  Type.Object(
    {
      requestId: idToken,
      quantity: Type.Union([Type.Literal("DISPLACEMENT"), Type.Literal("VELOCITY"), Type.Literal("REACTION_FORCE")]),
      target: targetNode,
      component: xyComponent,
    },
    { additionalProperties: false },
  ),
  Type.Object(
    { requestId: idToken, quantity: Type.Literal("REACTION_MOMENT"), target: targetNode, component: Type.Literal("Z") },
    { additionalProperties: false },
  ),
  Type.Object(
    {
      requestId: idToken,
      quantity: Type.Literal("GENERALIZED_FORCE"),
      target: targetElement,
      component: generalizedComponent,
      location: endLocation,
    },
    { additionalProperties: false },
  ),
]);
const transientNodalResultRequest = Type.Union([
  transientCommonResultRequest,
  Type.Object(
    { requestId: idToken, quantity: Type.Literal("ACCELERATION"), target: targetNode, component: xyComponent },
    { additionalProperties: false },
  ),
]);
const transientBaseResultRequest = Type.Union([
  transientCommonResultRequest,
  Type.Object(
    {
      requestId: idToken,
      quantity: Type.Union([Type.Literal("RELATIVE_ACCELERATION"), Type.Literal("ABSOLUTE_ACCELERATION")]),
      target: targetNode,
      component: xyComponent,
    },
    { additionalProperties: false },
  ),
]);
const analysisSpecV2TransientNodalSchema = Type.Object(
  {
    schemaVersion: Type.Literal("2.0"),
    kind: Type.Literal("engineering_analysis_spec"),
    modelSpecFingerprint,
    analysisType: Type.Literal("TRANSIENT"),
    units: forceUnits,
    definition: Type.Object(
      {
        time: transientTime,
        damping: transientDamping,
        excitation: Type.Object(
          {
            type: Type.Literal("NODAL_TIME_HISTORY"),
            nodeId: positiveId,
            component: xyComponent,
            quantity: Type.Literal("FORCE"),
            loadArtifact,
          },
          { additionalProperties: false },
        ),
      },
      { additionalProperties: false },
    ),
    resultRequests: Type.Array(transientNodalResultRequest, { minItems: 1 }),
  },
  { additionalProperties: false },
);
const analysisSpecV2TransientBaseSchema = Type.Object(
  {
    schemaVersion: Type.Literal("2.0"),
    kind: Type.Literal("engineering_analysis_spec"),
    modelSpecFingerprint,
    analysisType: Type.Literal("TRANSIENT"),
    units: emptyUnits,
    definition: Type.Object(
      {
        time: transientTime,
        damping: transientDamping,
        excitation: Type.Object(
          {
            type: Type.Literal("UNIFORM_BASE_EXCITATION"),
            component: xyComponent,
            quantity: Type.Literal("ACCELERATION"),
            loadArtifact,
          },
          { additionalProperties: false },
        ),
      },
      { additionalProperties: false },
    ),
    resultRequests: Type.Array(transientBaseResultRequest, { minItems: 1 }),
  },
  { additionalProperties: false },
);

const analysisSpecValidationSchema = Type.Union([
  analysisSpecV1Schema,
  analysisSpecV2StaticSchema,
  analysisSpecV2ModalSchema,
  analysisSpecV2TransientNodalSchema,
  analysisSpecV2TransientBaseSchema,
]);

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
      "Validate solver-neutral EngineeringAnalysisSpec V1 or V2 through the authoritative Python FEM core. SAFE and read-only; V2 validation is intrinsic only and does not render artifacts or execute a solver.",
    promptSnippet:
      "Validate explicit static, modal, or transient analysis intent separately from EngineeringModelSpec",
    promptGuidelines: [
      "Use V1 only for the legacy LINEAR_STATIC execution path. V2 supports intrinsic validation of LINEAR_STATIC, MODAL, and linear direct-integration TRANSIENT intent.",
      "A VALID V2 AnalysisSpec proves intrinsic solver-neutral validity only. V2 VALID does not establish READY, RENDERED, target existence, modal mass sufficiency, load-artifact integrity or time alignment, solver response mapping, or execution success.",
      "Do not invent load magnitudes, directions, target IDs, mode counts, damping coefficients, time steps, artifact hashes, result requests, units, or modelSpecFingerprint values merely to make a specification VALID.",
      "V2 MODAL supports EIGENVALUE, NATURAL_FREQUENCY, PERIOD, and NODE MODE_SHAPE X/Y/RZ requests. It does not imply that a bound model has adequate mass for eigensolution.",
      "V2 TRANSIENT supports only NODAL_TIME_HISTORY force or UNIFORM_BASE_EXCITATION acceleration with explicit NONE or RAYLEIGH damping. Uniform-base acceleration responses must state RELATIVE_ACCELERATION or ABSOLUTE_ACCELERATION rather than bare ACCELERATION.",
      "Intrinsic validation never reads ModelSpec targets or load artifact bytes. Cross-model binding, target existence, model readiness, artifact checks, and solver mapping belong to future V2 readiness profiles.",
      "This tool is read-only: it never writes OpenSees/APDL files, applies loads to a solver model, calls solver preflight/run, migrates specs, or repairs engineering facts.",
      "This fine-grained validation tool is temporary. The long-term Agent tool surface should converge into high-level Analysis capabilities instead of multiplying permanent internal tools.",
    ],
    parameters: Type.Object(
      { spec: analysisSpecValidationSchema },
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
      "Check or render a bound EngineeringModelSpec + supported EngineeringAnalysisSpec V1/V2 through one high-level OpenSees analysis preparation capability. CHECK is read-only. RENDER writes only controlled artifacts. Neither runs a solver.",
    promptSnippet:
      "Check joint analysis readiness or render deterministic OpenSees V1/V2 static, modal, or transient analysis bundles without executing them",
    promptGuidelines: [
      "CHECK is read-only and reruns authoritative ModelSpec validation, AnalysisSpec validation, Model Readiness, model fingerprint binding, unit compatibility, target existence, reaction restraint semantics, and proven OpenSees response mapping.",
      "RENDER writes only controlled artifacts below FEMagent's generated-analysis directory after the same readiness gate passes; callers cannot choose an artifact destination.",
      "Neither runs a solver. READY is not execution success, and RENDERED is not execution success; solver preflight and run remain separate controlled capabilities.",
      "Do not mutate engineering facts to force readiness. Never invent or alter supports, topology, node or element IDs, units, loads, result targets, or fingerprints just to make CHECK or RENDER pass.",
      "A NOT_READY or BLOCKED result is a deterministic engineering finding. Report the issue codes and preserve the submitted engineering facts rather than silently repairing them.",
      "This preparation tool accepts AnalysisSpec schemaVersion 1.0 only. V2 remains intrinsic-validation-only in PR27 and must not be admitted to this PR26 execution profile.",
      "V1 remains limited to bound 2D elastic-frame LINEAR_STATIC analysis with one explicit nodal-load case and the approved controlled result-request whitelist.",
    ],
    parameters: Type.Object(
      {
        mode: Type.Union([Type.Literal("CHECK"), Type.Literal("RENDER")]),
        modelSpec: modelSpecSchema,
        analysisSpec: analysisSpecValidationSchema,
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
