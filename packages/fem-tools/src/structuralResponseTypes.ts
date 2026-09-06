export type FemStructuralOperation = "SUMMARY" | "SERIES";

export type FemResultTarget =
  | { type: "NODE"; id: number }
  | { type: "ELEMENT"; id: number };

export type FemCartesianComponent = "X" | "Y" | "Z";
export type FemCartesianComponentInput =
  | FemCartesianComponent
  | "UX"
  | "UY"
  | "UZ"
  | "U1"
  | "U2"
  | "U3"
  | "1"
  | "2"
  | "3";
export type FemNodeCartesianQuantity =
  | "DISPLACEMENT"
  | "VELOCITY"
  | "ACCELERATION"
  | "REACTION_FORCE"
  | "REACTION_MOMENT";
export type FemStressComponent = "SX" | "SY" | "SZ" | "SXY" | "SYZ" | "SXZ";
export type FemPrincipalStressComponent = "S1" | "S2" | "S3" | "SINT" | "SEQV";
export type FemGeneralizedForceComponent = "N" | "VY" | "VZ" | "T" | "MY" | "MZ";
export type FemGeneralizedForceLocation = "END_I" | "END_J" | "SECTION";
export type FemDamperResponseComponent =
  | "FORCE"
  | "DEFORMATION"
  | "VELOCITY"
  | "DISSIPATED_ENERGY";
export type FemStructuralQuantity =
  | FemNodeCartesianQuantity
  | "STRESS"
  | "PRINCIPAL_STRESS"
  | "GENERALIZED_FORCE"
  | "DAMPER_RESPONSE";

interface FemPagedResultRequest {
  operation: FemStructuralOperation;
  offset?: number;
  limit?: number;
}

export interface FemNodeCartesianResultRequest extends FemPagedResultRequest {
  quantity: FemNodeCartesianQuantity;
  target: { type: "NODE"; id: number };
  component: FemCartesianComponentInput;
  location?: never;
}

export interface FemStressResultRequest extends FemPagedResultRequest {
  quantity: "STRESS";
  target: FemResultTarget;
  component: FemStressComponent;
  location?: never;
}

export interface FemPrincipalStressResultRequest extends FemPagedResultRequest {
  quantity: "PRINCIPAL_STRESS";
  target: FemResultTarget;
  component: FemPrincipalStressComponent;
  location?: never;
}

export interface FemGeneralizedForceResultRequest extends FemPagedResultRequest {
  quantity: "GENERALIZED_FORCE";
  target: { type: "ELEMENT"; id: number };
  component: FemGeneralizedForceComponent;
  location: FemGeneralizedForceLocation;
}

export interface FemDamperResponseResultRequest extends FemPagedResultRequest {
  quantity: "DAMPER_RESPONSE";
  target: { type: "ELEMENT"; id: number };
  component: FemDamperResponseComponent;
  location?: never;
}

export type FemStructuralResultQueryRequest =
  | FemNodeCartesianResultRequest
  | FemStressResultRequest
  | FemPrincipalStressResultRequest
  | FemGeneralizedForceResultRequest
  | FemDamperResponseResultRequest;
