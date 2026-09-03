import type { FemModelInspection as FemAnsysModelInspection } from "./bridgeProtocol.js";

export interface FemModelBundleFile {
  path: string;
  role: "ENTRYPOINT" | "PYTHON_MODULE" | "ENGINEERING_DATA" | "ANSYS_INCLUDE" | "UNKNOWN_DEPENDENCY" | string;
  sha256: string;
  sizeBytes: number;
}

export interface FemModelBundleDependency {
  source: string;
  reference: string;
  target: string | null;
  type: "PYTHON_IMPORT" | "PYTHON_FILE_READ" | "ANSYS_INPUT" | "ANSYS_USE" | string;
  status: "RESOLVED_WORKSPACE" | "EXTERNAL_PACKAGE" | "UNRESOLVED" | "BLOCKED_OUTSIDE_WORKSPACE" | string;
}

export interface FemModelBundleManifest {
  schemaVersion: "1.0";
  kind: "model_bundle_manifest";
  bundleId: string;
  entrypoint: { path: string; sha256: string };
  files: FemModelBundleFile[];
  dependencies: FemModelBundleDependency[];
  bundleFingerprint: string;
  integrity: "VALID" | "BLOCKED";
  warnings: string[];
}

export interface FemOpenSeesPythonModelInspection {
  schemaVersion: "1.0";
  kind: "opensees_python_model_inspection";
  inspectionLevel: "STATIC_PYTHON_AST_V1";
  format: "OPENSEES_PYTHON";
  classification: "MODEL_CONFIRMED" | "MODEL_LIKELY" | "NOT_OPENSEES_MODEL" | "UNSAFE";
  executionEligibility: "STATICALLY_ELIGIBLE" | "REQUIRES_BUILD_INSPECTION" | "INCOMPLETE" | "REJECTED";
  source: {
    path: string;
    fileName: string;
    suffix: ".py";
    sha256: string;
    sizeBytes: number;
    encoding: string;
  };
  apiSignals: Array<{ name: string; count: number }>;
  staticTopology: {
    nodeCount: number | null;
    elementCount: number | null;
    nodeTags: number[];
    elementTags: number[];
    basis: string;
  };
  dynamicGeneration: boolean;
  safetyFindings: Array<{ path: string; line: number; code: string; severity: "ERROR" }>;
  bundle: FemModelBundleManifest;
  warnings: string[];
}

export type FemAnyModelInspection = FemAnsysModelInspection | FemOpenSeesPythonModelInspection;
