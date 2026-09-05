import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { runFemCrossSolverValidation } from "@femagent/fem-tools";
import { Type } from "typebox";

const resultQuantity = Type.Union(
  [
    Type.Literal("DISPLACEMENT"),
    Type.Literal("VELOCITY"),
    Type.Literal("ACCELERATION"),
    Type.Literal("REACTION_FORCE"),
  ],
  { description: "Recorded nodal result quantity to compare" },
);

const resultOperation = Type.Union([Type.Literal("SUMMARY"), Type.Literal("SERIES")], {
  description: "PR14 V1 compares SUMMARY only; SERIES returns an explicit NOT_COMPARABLE limitation",
});

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
    description: "Compare two independently verified role-backed recorded FEM responses under the strict Cross-Solver Validation V1 compatibility contract. SAFE and read-only; never executes a solver.",
    promptSnippet: "Compare two recorded solver responses for the same explicit engineering semantic role without guessing units, mappings, or tolerances",
    promptGuidelines: [
      "Semantic roles must come from explicit supplied manifests; never infer or rewrite role mappings from names, coordinates, constraints, topology, or LLM judgment.",
      "This tool is SAFE/read-only and must never execute OpenSees or ANSYS.",
      "Never infer or convert result units. In particular, ANSYS unit=null remains unknown and makes V1 numerical comparison NOT_COMPARABLE.",
      "Never treat either side as ground truth and never rank solver trustworthiness from the returned deltas.",
      "Do not declare engineering PASS/FAIL unless a separate future policy supplies an explicit tolerance; PR14 V1 has no tolerance policy.",
      "NOT_COMPARABLE is a limitation record, not evidence that either solver is wrong.",
      "Preserve Semantic Role, Result Intelligence, and Engineering Evidence hard errors such as stale manifests, run/model mismatch, and artifact hash mismatch.",
    ],
    parameters: Type.Object({
      projectId: Type.String({ description: "Caller-defined project identifier" }),
      left: side,
      right: side,
      quantity: resultQuantity,
      component: Type.String({ description: "Cartesian component alias such as X, UX, U1, or 1" }),
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
          operation: params.operation,
        },
        signal,
      );
      return { content: [{ type: "text", text: JSON.stringify(report, null, 2) }], details: report };
    },
  });
}
