import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runFemModelSpecReadiness,
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
      "Use fem_model_spec_readiness after a proposed spec is valid when you need the deterministic V1 renderer-admission check for connectivity and planar rigid-body restraint.",
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

  pi.registerTool({
    name: "fem_model_spec_readiness",
    label: "Check FEM Model Readiness",
    description:
      "Evaluate deterministic engineering readiness of a V1 2D planar elastic-frame ModelSpec through the authoritative Python FEM core. SAFE and read-only; it checks connectivity and planar rigid-body restraint without rendering or running a solver.",
    promptSnippet:
      "Check whether a valid 2D elastic-frame ModelSpec is ready to enter controlled renderer authoring",
    promptGuidelines: [
      "Call this tool to evaluate renderer-admission readiness after or alongside ModelSpec validation; the Python core always re-runs PR21 validation internally, so validation cannot be bypassed.",
      "READY means only that the V1 connectivity and per-component planar rigid-body restraint checks passed. It does not prove structural adequacy, analysis correctness, numerical conditioning, or solver success.",
      "NOT_READY is a deterministic engineering finding, not permission to invent or automatically insert support constraints, merge nodes, join components, or alter topology.",
      "Disconnected components and repeated node-pair connectivity may be warnings rather than errors; report them exactly and do not silently repair them.",
      "Do not infer missing engineering facts, units, support types, or Semantic Roles from geometry, names, conventions, or retrieved knowledge.",
      "This tool never writes OpenSees/APDL files and never executes OpenSees or ANSYS.",
    ],
    parameters: Type.Object(
      {
        spec: modelSpecSchema,
      },
      { additionalProperties: false },
    ),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemModelSpecReadiness(
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
