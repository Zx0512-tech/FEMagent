import type { FemResultOperation } from "./resultTypes.js";
import type {
  FemGeneralizedForceLocation,
  FemResultTarget,
} from "./structuralResponseTypes.js";

export type FemCrossSolverValidationStatus = "COMPARABLE" | "NOT_COMPARABLE";

export interface FemCrossSolverSideRequest {
  modelPath: string;
  manifestPath: string;
  roleId: string;
  runRef: string;
}

export interface FemCrossSolverQueryRequest {
  quantity: string;
  component: string;
  location?: FemGeneralizedForceLocation;
  operation: FemResultOperation;
}

export interface FemCrossSolverLimitation {
  code: string;
  message: string;
}

export interface FemCrossSolverSideProjection {
  solver: string | null;
  runId: string | null;
  modelBundleFingerprint: string | null;
  entity: FemResultTarget | null;
  unit: string | null;
  referenceFrame: string | null;
  absolutePeak: number | null;
}

export interface FemCrossSolverComparison {
  metric: "absolutePeak";
  left: number;
  right: number;
  absoluteDifference: number;
  relativeDifference: number;
}

export interface FemCrossSolverValidationReport {
  schemaVersion: "1.0";
  kind: "cross_solver_validation";
  status: FemCrossSolverValidationStatus;
  projectId: string;
  role: { roleId: string | null; roleType: string | null } | null;
  query: FemCrossSolverQueryRequest;
  sides: {
    left: FemCrossSolverSideProjection | null;
    right: FemCrossSolverSideProjection | null;
  };
  comparison: FemCrossSolverComparison | null;
  limitations: FemCrossSolverLimitation[];
}
