import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  runFemRoleEvidenceProject,
  runFemSemanticInspect,
  runFemSemanticResolve,
  type FemRoleEvidenceQueryRequest,
} from "@femagent/fem-tools";
import { Type } from "typebox";

const resultQuantity = Type.Union(
  [
    Type.Literal("DISPLACEMENT"),
    Type.Literal("VELOCITY"),
    Type.Literal("ACCELERATION"),
    Type.Literal("REACTION_FORCE"),
    Type.Literal("REACTION_MOMENT"),
    Type.Literal("STRESS"),
    Type.Literal("PRINCIPAL_STRESS"),
    Type.Literal("GENERALIZED_FORCE"),
    Type.Literal("DAMPER_RESPONSE"),
  ],
  { description: "Recorded NODE/ELEMENT structural response quantity to query through a resolved semantic role" },
);

const structuralComponent = Type.Union([
  Type.Literal("X"), Type.Literal("Y"), Type.Literal("Z"),
  Type.Literal("UX"), Type.Literal("UY"), Type.Literal("UZ"),
  Type.Literal("U1"), Type.Literal("U2"), Type.Literal("U3"),
  Type.Literal("1"), Type.Literal("2"), Type.Literal("3"),
  Type.Literal("SX"), Type.Literal("SY"), Type.Literal("SZ"),
  Type.Literal("SXY"), Type.Literal("SYZ"), Type.Literal("SXZ"),
  Type.Literal("S1"), Type.Literal("S2"), Type.Literal("S3"),
  Type.Literal("SINT"), Type.Literal("SEQV"),
  Type.Literal("N"), Type.Literal("VY"), Type.Literal("VZ"),
  Type.Literal("T"), Type.Literal("MY"), Type.Literal("MZ"),
  Type.Literal("FORCE"), Type.Literal("DEFORMATION"), Type.Literal("VELOCITY"),
  Type.Literal("DISSIPATED_ENERGY"),
]);

const resultOperation = Type.Union([Type.Literal("SUMMARY"), Type.Literal("SERIES")], {
  description: "Return extrema/peak summary or a bounded recorded series slice",
});

const generalizedLocation = Type.Union([
  Type.Literal("END_I"), Type.Literal("END_J"), Type.Literal("SECTION"),
]);

const semanticInputs = {
  modelPath: Type.String({ description: "Workspace-relative FEM model entrypoint path" }),
  manifestPath: Type.String({ description: "Workspace-relative explicit Semantic Role Manifest path" }),
};

export default function semanticToolsExtension(pi: ExtensionAPI) {
  pi.registerTool({
    name: "fem_semantic_inspect",
    label: "Inspect FEM Semantic Roles",
    description: "Validate an explicit Engineering Semantic Role Manifest against the exact current Model Bundle. Supports explicit NODE and ELEMENT roles. SAFE and read-only; no role inference or solver execution.",
    promptSnippet: "Inspect explicit engineering-role declarations before resolving role-based result targets",
    promptGuidelines: [
      "Semantic roles are explicit user/project declarations, not model-name, coordinate, constraint, topology, or LLM inferences.",
      "Never rewrite or auto-complete the Semantic Role Manifest from this tool.",
      "Preserve stale-model and invalid-manifest failures instead of guessing a replacement role mapping.",
      "NOT_STATICALLY_ENUMERABLE means the explicit declaration is retained without static entity confirmation; do not describe that as solver-verified topology.",
      "This tool is SAFE/read-only and must never invoke OpenSees or ANSYS execution.",
    ],
    parameters: Type.Object(semanticInputs),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemSemanticInspect(ctx.cwd, params.modelPath, params.manifestPath, signal);
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });

  pi.registerTool({
    name: "fem_semantic_resolve",
    label: "Resolve FEM Semantic Role",
    description: "Resolve one explicitly declared engineering role to its solver-native NODE or ELEMENT identity after exact Model Bundle fingerprint validation. SAFE and read-only.",
    promptSnippet: "Resolve an explicit engineering role to a deterministic solver entity without heuristic guessing",
    promptGuidelines: [
      "Use only role IDs declared in the supplied Semantic Role Manifest; never infer a role from component names, variable names, coordinates, constraints, node numbering, or element numbering.",
      "A SEMANTIC_ROLE_MODEL_MISMATCH means the manifest is stale for the current model and must not be bypassed.",
      "A SEMANTIC_ROLE_ENTITY_NOT_FOUND means a statically enumerable model disproves the declared entity identity; do not substitute another NODE or ELEMENT.",
      "Never rewrite the manifest and never invoke a solver from this tool.",
    ],
    parameters: Type.Object({
      ...semanticInputs,
      roleId: Type.String({ description: "Explicit roleId such as TOWER_BASE_LEFT or GIRDER_MIDSPAN" }),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemSemanticResolve(
        ctx.cwd,
        params.modelPath,
        params.manifestPath,
        params.roleId,
        signal,
      );
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });

  pi.registerTool({
    name: "fem_evidence_project_role",
    label: "Project Role-backed FEM Evidence",
    description: "Resolve an explicit NODE/ELEMENT semantic role, require the recorded run to belong to the same Model Bundle, then project the recorded structural response through artifact-verified Evidence Center. SAFE and read-only.",
    promptSnippet: "Produce auditable engineering evidence for an explicitly declared NODE or ELEMENT engineering role",
    promptGuidelines: [
      "Use this tool only with an explicit Semantic Role Manifest; never guess role-to-NODE or role-to-ELEMENT mappings.",
      "The current model fingerprint, recorded run model fingerprint, and semantic manifest fingerprint must agree before evidence is projected.",
      "Use location only for canonical GENERALIZED_FORCE identities such as END_I, END_J, or SECTION; never infer local-axis/end semantics.",
      "Preserve SEMANTIC_ROLE_RUN_MODEL_MISMATCH and artifact-integrity failures; never downgrade or invent evidence.",
      "Only VERIFIED evidence may be described as verified engineering evidence.",
      "If the returned metric unit is null, report the unit as unknown; never infer ANSYS units from model conventions or magnitude.",
      "This tool is SAFE/read-only and never reruns OpenSees or ANSYS.",
    ],
    parameters: Type.Object({
      projectId: Type.String({ description: "Caller-defined project identifier" }),
      ...semanticInputs,
      roleId: Type.String({ description: "Explicit semantic roleId" }),
      runRef: Type.String({ description: "run_<id>, workspace-relative run directory, or run_manifest.json path" }),
      evidenceId: Type.String({ description: "Stable caller-defined evidence identifier" }),
      quantity: resultQuantity,
      component: structuralComponent,
      location: Type.Optional(generalizedLocation),
      operation: resultOperation,
      offset: Type.Optional(Type.Integer({ minimum: 0, description: "SERIES starting sample offset" })),
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 5000, description: "SERIES maximum returned samples" })),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const query = {
        quantity: params.quantity,
        component: params.component,
        ...(params.location === undefined ? {} : { location: params.location }),
        operation: params.operation,
        ...(params.offset === undefined ? {} : { offset: params.offset }),
        ...(params.limit === undefined ? {} : { limit: params.limit }),
      } as FemRoleEvidenceQueryRequest;
      const report = await runFemRoleEvidenceProject(
        ctx.cwd,
        params.projectId,
        params.modelPath,
        params.manifestPath,
        params.roleId,
        params.runRef,
        params.evidenceId,
        query,
        signal,
      );
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });
}
