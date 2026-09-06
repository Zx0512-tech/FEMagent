import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { runFemCrossSolverValidation } from "@femagent/fem-tools";
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
  { description: "Recorded NODE/ELEMENT result quantity to compare" },
);

const resultOperation = Type.Union([Type.Literal("SUMMARY"), Type.Literal("SERIES")], {
  description: "V1 compares SUMMARY only; SERIES returns an explicit NOT_COMPARABLE limitation",
});

const location = Type.Union([
  Type.Literal("END_I"), Type.Literal("END_J"), Type.Literal("SECTION"),
]);

const side = Type.Object({
  modelPath: Type.String({ description: "Workspace-relative model entrypoint for this solver side" }),
  manifestPath: Type.String({ description: "Workspace-relative explicit Semantic Role Manifest for this side" }),
  roleId: Type.String({ description: "Explicit engineering semantic role ID" }),
  runRef: Type.String({ description: "Completed recorded FEMagent solver run reference" }),
});

export default function validationToolsExtension(pi: ExtensionAPI) {
  pi.registerTool({
    name: "fem_cross_solver_validate",
    label: "Validate FEM Cross-Solver Results",
    description: "Compare two independently verified role-backed NODE/ELEMENT recorded responses under strict Cross-Solver compatibility. SAFE and read-only; never executes a solver.",
    promptSnippet: "Compare two recorded solver responses for the same explicit engineering semantic role without guessing units, mappings, locations, or tolerances",
    promptGuidelines: [
      "Semantic roles must come from explicit supplied manifests; never infer or rewrite role mappings from names, coordinates, constraints, topology, or LLM judgment.",
      "For structural element responses, location and stress semantics must match exactly; never equate END_I with END_J or different averaging semantics.",
      "This tool is SAFE/read-only and must never execute OpenSees or ANSYS.",
      "Never infer or convert result units. In particular, ANSYS unit=null remains unknown and makes numerical comparison NOT_COMPARABLE.",
      "Never treat either side as ground truth and never rank solver trustworthiness from the returned deltas.",
      "Do not declare engineering PASS/FAIL unless a separate policy supplies an explicit tolerance; V1 has no tolerance policy.",
      "NOT_COMPARABLE is a limitation record, not evidence that either solver is wrong.",
      "Preserve Semantic Role, Result Intelligence, and Engineering Evidence hard errors such as stale manifests, run/model mismatch, and artifact hash mismatch.",
    ],
    parameters: Type.Object({
      projectId: Type.String({ description: "Caller-defined project identifier" }),
      left: side,
      right: side,
      quantity: resultQuantity,
      component: Type.String({ description: "Canonical recorded component such as X, SEQV, or MZ" }),
      location: Type.Optional(location),
      operation: resultOperation,
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const report = await runFemCrossSolverValidation(
        ctx.cwd,
        params.projectId,
        params.left,
        params.right,
        {
          quantity: params.quantity,
          component: params.component,
          ...(params.location === undefined ? {} : { location: params.location }),
          operation: params.operation,
        },
        signal,
      );
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });
}
