import type { FemResultOperation } from "./resultTypes.js";

export type FemSemanticRoleType =
  | "TOWER_BASE"
  | "GIRDER_END"
  | "BEARING"
  | "DAMPER_ATTACHMENT"
  | "MIDSPAN"
  | "SUPPORT";

export type FemSemanticRoleStatus = "RESOLVED" | "UNRESOLVED" | "INVALID" | "STALE_MODEL";
export type FemSemanticEntityValidation = "STATICALLY_CONFIRMED" | "NOT_STATICALLY_ENUMERABLE";

export interface FemSemanticRoleEntity {
  type: "NODE";
  id: number;
}

export interface FemSemanticRoleRecord {
  roleId: string;
  roleType: FemSemanticRoleType;
  entity: FemSemanticRoleEntity;
  status: FemSemanticRoleStatus;
  entityValidation: FemSemanticEntityValidation;
  modelBundleFingerprint: string;
  manifestSha256: string;
}

export interface FemSemanticRoleResolution extends FemSemanticRoleRecord {
  schemaVersion: "1.0";
  kind: "semantic_role_resolution";
}

export interface FemSemanticRoleInspection {
  schemaVersion: "1.0";
  kind: "semantic_role_inspection";
  status: "RESOLVED" | "UNRESOLVED";
  model: {
    path: string;
    bundleFingerprint: string;
  };
  manifest: {
    path: string;
    sha256: string;
  };
  roles: FemSemanticRoleRecord[];
  warnings: Array<{ code: string; message: string }>;
}

export interface FemRoleEvidenceQueryRequest {
  quantity: "DISPLACEMENT" | "VELOCITY" | "ACCELERATION" | "REACTION_FORCE" | string;
  component: string;
  operation: FemResultOperation;
  offset?: number;
  limit?: number;
}
