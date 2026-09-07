import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runFemModelSpecValidate,
  type FemEngineeringModelSpecInput,
} from "@femagent/fem-tools";
import { Type } from "typebox";

const positiveId = Type.Integer({ minimum: 1 });
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

export default function modelSpecToolsExtension(pi: ExtensionAPI) {
  pi.registerTool({
    name: "fem_model_spec_validate",
    label: "Validate FEM Model Specification",
    description:
      "Validate a proposed V1 2D planar elastic-frame EngineeringModelSpec through the authoritative Python FEM core. SAFE and read-only; it does not write a model or execute a solver.",
    promptSnippet:
      "Validate explicit engineering model facts before any future solver-specific model rendering",
    promptGuidelines: [
      "Do not invent missing Young's modulus, section area, Iz, support constraints, nodal masses, topology, or other critical engineering facts merely to make a ModelSpec VALID.",
      "Do not infer units from numeric magnitude or common engineering convention. Every ModelSpec unit declaration must come from explicit project/user context.",
      "Knowledge retrieval may provide guidance or recommended values, but retrieved knowledge is not confirmed ModelSpec truth unless the user/project explicitly adopts it.",
      "VALID means only that the V1 deterministic ModelSpec contract is internally consistent. It does not prove structural stability, adequacy, solver readiness, or numerical correctness.",
      "Do not infer Semantic Roles such as SUPPORT, COLUMN, GIRDER_END, or TOWER_BASE from coordinates, orientation, constraints, or names.",
      "This tool never writes OpenSees/APDL files and never executes OpenSees or ANSYS.",
    ],
    parameters: Type.Object(
      {
        spec: modelSpecSchema,
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemModelSpecValidate(
        ctx.cwd,
        params.spec as FemEngineeringModelSpecInput,
        signal,
      );
      return {
        content: [{ type: "text", text: JSON.stringify(report, null, 2) }],
        details: report,
      };
    },
  });
}
