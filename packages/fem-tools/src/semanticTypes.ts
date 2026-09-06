import type {
  FemDamperResponseComponent,
  FemGeneralizedForceComponent,
  FemGeneralizedForceLocation,
  FemNodeCartesianQuantity,
  FemPrincipalStressComponent,
  FemResultTarget,
  FemStressComponent,
  FemStructuralOperation,
} from "./structuralResponseTypes.js";

export type FemSemanticRoleType =
  | "TOWER_BASE"
  | "GIRDER_END"
  | "BEARING"
  | "DAMPER_ATTACHMENT"
  | "MIDSPAN"
  | "SUPPORT";

export type FemSemanticRoleStatus = "RESOLVED" | "UNRESOLVED" | "INVALID" | "STALE_MODEL";
export type FemSemanticEntityValidation = "STATICALLY_CONFIRMED" | "NOT_STATICALLY_ENUMERABLE";

export type FemSemanticRoleEntity = FemResultTarget;

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

type FemRoleEvidencePaging = {
  operation: FemStructuralOperation;
  offset?: number;
  limit?: number;
};

export type FemRoleEvidenceQueryRequest =
  | (FemRoleEvidencePaging & {
      quantity: FemNodeCartesianQuantity;
      component: string;
      location?: never;
    })
  | (FemRoleEvidencePaging & {
      quantity: "STRESS";
      component: FemStressComponent;
      location?: never;
    })
  | (FemRoleEvidencePaging & {
      quantity: "PRINCIPAL_STRESS";
      component: FemPrincipalStressComponent;
      location?: never;
    })
  | (FemRoleEvidencePaging & {
      quantity: "GENERALIZED_FORCE";
      component: FemGeneralizedForceComponent;
      location: FemGeneralizedForceLocation;
    })
  | (FemRoleEvidencePaging & {
      quantity: "DAMPER_RESPONSE";
      component: FemDamperResponseComponent;
      location?: never;
    });
