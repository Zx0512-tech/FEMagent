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

export type FemModelValidationStatus = "PASSED" | "LIMITED" | "REJECTED";
export type FemModelExecutionEligibility =
  | "STATICALLY_ELIGIBLE"
  | "REQUIRES_SOLVER_INSPECTION"
  | "INCOMPLETE"
  | "REJECTED";

export interface FemModelManifest {
  schemaVersion: "1.0";
  modelFormat: "ANSYS_APDL_TEXT";
  solverCompatibility: {
    ansys:
      | "STATIC_TEXT_COMPATIBLE"
      | "REQUIRES_SOLVER_INSPECTION"
      | "INCOMPLETE_MODEL"
      | "REJECTED_UNSAFE";
    opensees: "NOT_DIRECTLY_COMPATIBLE";
  };
  topology: {
    nodeCount: { value: number | null; basis: string };
    elementCount: { value: number | null; basis: string };
    coordinateBounds: null | {
      basis: "EXPLICIT_NUMERIC_N_COMMANDS";
      sampledNodeCount: number;
      x: { min: number; max: number };
      y: { min: number; max: number };
      z: { min: number; max: number };
    };
    elementTypes: Array<{ id: string; name: string }>;
  };
  materials: Array<{ id: string; properties: string[] }>;
  sections: Array<{
    id: string;
    type: string;
    subtype: string | null;
    name: string | null;
  }>;
  components: Array<{ name: string; entity: string }>;
  boundaries: {
    explicitConstraintCommandCount: number;
    labels: string[];
  };
  existingLoadSignals: Array<{ command: string; count: number }>;
  generation: {
    parametric: boolean;
    blockBased: boolean;
    doLoopCount: number;
  };
  warnings: string[];
}

export interface FemModelInspection {
  schemaVersion: "1.1";
  kind: "model_inspection";
  inspectionLevel: "STATIC_APDL_V1";
  format: "ANSYS_APDL_TEXT";
  source: {
    path: string;
    fileName: string;
    suffix: string;
    sha256: string;
    sizeBytes: number;
    encoding: string;
  };
  validation: {
    status: FemModelValidationStatus;
    executionEligibility: FemModelExecutionEligibility;
    checks: {
      prep7: "PASSED" | "FAILED";
      nodeDefinitions: "PASSED" | "FAILED";
      elementDefinitions: "PASSED" | "FAILED";
      forbiddenCommandScan: "PASSED" | "FAILED";
    };
    issues: Array<{ code: string; severity: "ERROR" | "INFO" }>;
    forbiddenCommands: Array<{ line: number; marker: string; command: string }>;
  };
  summary: {
    lineCount: number;
    explicitNodeCommandCount: number;
    explicitElementCommandCount: number;
    nodeBlockCount: number;
    elementBlockCount: number;
    doLoopCount: number;
    parametricModel: boolean;
    blockBasedModel: boolean;
    materialDefinitionCount: number;
    sectionDefinitionCount: number;
    componentDefinitionCount: number;
    explicitConstraintCommandCount: number;
  };
  manifest: FemModelManifest;
}

export interface FemLoadMappingSuggestion {
  mapping: {
    version?: number;
    loadKind?: string | null;
    timeColumn?: string | null;
    timeUnit?: string | null;
    timeStepS?: number | null;
    valueColumn?: string | null;
    quantity?: string | null;
    sourceUnit?: string | null;
    applicationType?: string | null;
    component?: string | null;
    scale?: number;
  };
  confidence: "HIGH" | "MEDIUM" | "LOW";
  reasons: string[];
  warnings: string[];
  alternatives: Record<string, unknown>;
  unitSource: string;
  standardizeDecision: "ASK" | "AUTO";
  requiredConfirmations: string[];
}

export interface FemLoadManifest {
  schemaVersion: "1.0";
  kind: "load_manifest";
  source: {
    path: string;
    fileName: string;
    suffix: string;
    sha256: string;
    sizeBytes: number;
    encoding: string | null;
  };
  format: string;
  selfDescribing: boolean;
  structure: {
    rowCount: number;
    columnCount: number;
    columns: string[];
    delimiter: string | null;
    hasHeader: boolean;
  };
  time: {
    column: string | null;
    stepS: number | null;
    uniform: boolean;
    sourceUnit: string | null;
    basis: string;
  };
  channels: Array<{
    column: string;
    numericCount: number;
    missingCount: number;
    min: number | null;
    max: number | null;
    unitHint: string | null;
    quantityHint: string | null;
    selectedBySuggestion: boolean;
  }>;
  declaredMetadata: Record<string, unknown>;
  suggestedMapping: FemLoadMappingSuggestion;
  warnings: string[];
}

export interface FemLoadInspection {
  schemaVersion: "1.1";
  kind: "load_inspection";
  inspectionLevel: "TABULAR_DATA" | "SELF_DESCRIBING_RECORD";
  format: string;
  source: FemLoadManifest["source"];
  rowCount: number;
  columnCount: number;
  delimiter: string | null;
  hasHeader: boolean;
  columns: Array<{
    name: string;
    numericCount: number;
    missingCount: number;
    min: number | null;
    max: number | null;
    unitHint: string | null;
    timeCandidate: boolean;
  }>;
  sampleRows: Array<Record<string, string>>;
  declaredMetadata: Record<string, unknown>;
  suggestedMapping: FemLoadMappingSuggestion;
  manifest: FemLoadManifest;
  warnings: string[];
}

export interface FemStandardizedLoad {
  schemaVersion: "1.0";
  kind: "standardized_load";
  format: "FEMAGENT_LOAD_CSV_V1";
  source: {
    path: string;
    fileName: string;
    sha256: string;
    format: string;
  };
  output: {
    path: string;
    sha256: string;
    sizeBytes: number;
    encoding: "utf-8";
    delimiter: ",";
  };
  loadKind: string;
  sampleCount: number;
  channelCount: number;
  outputRowCount: number;
  time: {
    startS: number;
    endS: number;
    strictlyIncreasing: true;
    source: Record<string, unknown>;
  };
  channels: Array<Record<string, unknown>>;
  validation: { nanCount: 0; timeStrictlyIncreasing: true };
}
