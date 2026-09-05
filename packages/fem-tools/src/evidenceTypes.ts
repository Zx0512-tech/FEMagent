import type { FemResultOperation, FemResultQuerySummary } from "./resultTypes.js";

export type FemEvidenceStatus = "VERIFIED" | "INVALID" | "LIMITED" | "UNVERIFIED";

export interface FemEvidenceArtifactRef {
  artifact: string;
  sha256: string | null;
  entity: Record<string, unknown>;
}

export interface FemEngineeringEvidenceMetric {
  quantity?: string;
  target?: { type: "NODE"; id: number };
  component?: string;
  unit?: string | null;
  referenceFrame?: string;
  operation?: FemResultOperation;
  abscissa?: { semantic: string; unit: string | null };
  summary?: FemResultQuerySummary;
  series?: Array<{ abscissa: number; value: number }>;
  value?: number;
  [key: string]: unknown;
}

export interface FemEngineeringEvidence {
  evidenceId: string;
  claim: string;
  status: FemEvidenceStatus;
  artifacts: FemEvidenceArtifactRef[];
  metric: FemEngineeringEvidenceMetric;
  provenance: Record<string, unknown> & {
    runId?: string;
    caseFingerprint?: string;
    solver?: string;
  };
}

export interface FemEngineeringEvidenceReport {
  projectId: string;
  solverRuns: Array<{
    runId: string;
    solver: string;
    caseFingerprint: string;
  }>;
  verifiedEvidence: FemEngineeringEvidence[];
  limitations: Array<{
    evidenceId: string;
    status: FemEvidenceStatus;
    claim: string;
  }>;
}
