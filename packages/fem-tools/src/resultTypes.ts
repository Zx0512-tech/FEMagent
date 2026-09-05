export type FemResultIntegrityStatus = "VALID" | "LIMITED" | "INVALID";
export type FemResultOperation = "SUMMARY" | "SERIES";

export interface FemResultArtifact {
  role: string;
  path: string;
  sha256: string;
  declaredSha256: string | null;
  status: "VERIFIED" | "PRESENT_UNHASHED";
}

export interface FemResultCapability {
  quantity: string;
  component: string;
  target: Record<string, unknown>;
  unit: string | null;
  referenceFrame: string;
  sourceColumn?: string;
  sourceArtifact?: string;
}

export interface FemResultManifest {
  schemaVersion: "1.0";
  kind: "result_manifest";
  runId: string;
  caseFingerprint: string;
  runManifest: string;
  solver: Record<string, unknown> & { name: string };
  model: {
    path: string | null;
    bundleFingerprint: string | null;
  };
  integrity: {
    status: FemResultIntegrityStatus;
    artifacts: FemResultArtifact[];
  };
  abscissa: null | {
    semantic: string;
    unit: string | null;
    sampleCount: number;
    start: number | null;
    end: number | null;
  };
  queryCapabilities: FemResultCapability[];
  observations: Record<string, unknown>;
  warnings: Array<{ code: string; message: string; [key: string]: unknown }>;
}

export interface FemResultQueryRequest {
  quantity: "DISPLACEMENT" | "VELOCITY" | "ACCELERATION" | "REACTION_FORCE" | string;
  target: { type: "NODE"; id: number };
  component: string;
  operation: FemResultOperation;
  offset?: number;
  limit?: number;
}

export interface FemResultQuerySummary {
  sampleCount: number;
  min: number;
  max: number;
  absolutePeak: number;
  abscissaAtAbsolutePeak: number;
}

export interface FemResultQuery {
  schemaVersion: "1.0";
  kind: "result_query";
  runId: string;
  caseFingerprint: string;
  solver: Record<string, unknown> & { name: string };
  quantity: string;
  target: { type: "NODE"; id: number };
  component: string;
  operation: FemResultOperation;
  unit: string | null;
  referenceFrame: string;
  abscissa: { semantic: string; unit: string | null };
  source: Record<string, unknown>;
  summary?: FemResultQuerySummary;
  series?: Array<{ abscissa: number; value: number }>;
  paging?: { offset: number; limit: number; returned: number; total: number };
}
