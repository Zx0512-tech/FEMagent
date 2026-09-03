export const FEM_BRIDGE_PROTOCOL = "femagent.bridge/v1" as const;
export const DEFAULT_BRIDGE_TIMEOUT_MS = 10_000;

export interface FemBridgeMeta {
  coreVersion: string;
  command: string;
}

export interface FemBridgeSuccess<T> {
  protocol: typeof FEM_BRIDGE_PROTOCOL;
  requestId: string;
  ok: true;
  result: T;
  meta: FemBridgeMeta;
}

export interface FemBridgeFailure {
  protocol: typeof FEM_BRIDGE_PROTOCOL;
  requestId: string;
  ok: false;
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
  meta: FemBridgeMeta;
}

export type FemBridgeEnvelope<T> = FemBridgeSuccess<T> | FemBridgeFailure;

export interface FemHealth {
  status: "ok";
  core: "fem_core";
  coreVersion: string;
  python: { version: string; implementation: string };
  platform: string;
  solvers: { ansys: "not_checked"; opensees: "not_checked" };
}

export interface FemModelInspection {
  schemaVersion: "1.0";
  kind: "model_inspection";
  inspectionLevel: "STATIC_TEXT_ONLY";
  format: "ANSYS_APDL_TEXT";
  source: {
    path: string;
    fileName: string;
    suffix: string;
    sha256: string;
    sizeBytes: number;
    encoding: string;
  };
  summary: {
    lineCount: number;
    explicitNodeCommandCount: number;
    explicitElementCommandCount: number;
    blockCommandCount: number;
    doLoopCount: number;
    parametricSignals: boolean;
  };
  elementTypes: string[];
  signals: { hasPrep7: boolean };
  warnings: string[];
}

export interface FemLoadInspection {
  schemaVersion: "1.0";
  kind: "load_inspection";
  inspectionLevel: "TABULAR_TEXT";
  format: string;
  source: {
    path: string;
    fileName: string;
    suffix: string;
    sha256: string;
    sizeBytes: number;
    encoding: string;
  };
  rowCount: number;
  columnCount: number;
  delimiter: string;
  hasHeader: boolean;
  columns: Array<{
    name: string;
    numericCount: number;
    missingCount: number;
    min: number | null;
    max: number | null;
    timeCandidate: boolean;
  }>;
  sampleRows: Array<Record<string, string>>;
  warnings: string[];
}
