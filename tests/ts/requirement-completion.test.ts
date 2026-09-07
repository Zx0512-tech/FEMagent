import assert from "node:assert/strict";
import test from "node:test";

import {
  runFemRequirementComplete,
  type FemEngineeringRequirementCompletion,
  type FemEngineeringRequirementDraft,
} from "@femagent/fem-tools";

function incompleteBeamDraft(): FemEngineeringRequirementDraft {
  return {
    schema: "FEMAGENT_ENGINEERING_REQUIREMENT_DRAFT_V1",
    profile: "FRAME_2D_REQUIREMENT_V1",
    sources: [
      {
        sourceId: "source_1",
        kind: "USER_MESSAGE",
        text: "建立一个15m简支梁",
      },
    ],
    templateIntent: {
      templateId: "SIMPLY_SUPPORTED_BEAM_2D_V1",
      evidence: { sourceId: "source_1", quote: "简支梁" },
    },
    facts: [
      {
        kind: "SPAN",
        source: "USER_EXPLICIT",
        value: 15,
        unit: "m",
        evidence: { sourceId: "source_1", quote: "15m" },
      },
    ],
  };
}

function completeBeamDraft(): FemEngineeringRequirementDraft {
  return {
    schema: "FEMAGENT_ENGINEERING_REQUIREMENT_DRAFT_V1",
    profile: "FRAME_2D_REQUIREMENT_V1",
    sources: [
      {
        sourceId: "source_1",
        kind: "USER_MESSAGE",
        text: "建立一个15m简支梁",
      },
      {
        sourceId: "source_2",
        kind: "USER_MESSAGE",
        text: "单位用m、N、s，E=2.06e11 Pa，A=0.02m²，Iz=8e-5m⁴",
      },
    ],
    templateIntent: {
      templateId: "SIMPLY_SUPPORTED_BEAM_2D_V1",
      evidence: { sourceId: "source_1", quote: "简支梁" },
    },
    facts: [
      {
        kind: "SPAN",
        source: "USER_EXPLICIT",
        value: 15,
        unit: "m",
        evidence: { sourceId: "source_1", quote: "15m" },
      },
      {
        kind: "UNIT_DECLARATION",
        source: "USER_EXPLICIT",
        dimension: "length",
        value: "m",
        evidence: { sourceId: "source_2", quote: "单位用m、N、s" },
      },
      {
        kind: "UNIT_DECLARATION",
        source: "USER_EXPLICIT",
        dimension: "force",
        value: "N",
        evidence: { sourceId: "source_2", quote: "单位用m、N、s" },
      },
      {
        kind: "UNIT_DECLARATION",
        source: "USER_EXPLICIT",
        dimension: "time",
        value: "s",
        evidence: { sourceId: "source_2", quote: "单位用m、N、s" },
      },
      {
        kind: "YOUNGS_MODULUS",
        source: "USER_EXPLICIT",
        value: 2.06e11,
        unit: "Pa",
        evidence: { sourceId: "source_2", quote: "E=2.06e11 Pa" },
      },
      {
        kind: "SECTION_AREA",
        source: "USER_EXPLICIT",
        value: 0.02,
        unit: "m²",
        evidence: { sourceId: "source_2", quote: "A=0.02m²" },
      },
      {
        kind: "SECTION_IZ",
        source: "USER_EXPLICIT",
        value: 8e-5,
        unit: "m⁴",
        evidence: { sourceId: "source_2", quote: "Iz=8e-5m⁴" },
      },
    ],
  };
}

test("incomplete requirement crosses the real TypeScript/Python bridge", async () => {
  const result: FemEngineeringRequirementCompletion = await runFemRequirementComplete(
    process.cwd(),
    incompleteBeamDraft(),
  );

  assert.equal(result.schema, "FEMAGENT_ENGINEERING_REQUIREMENT_COMPLETION_V1");
  assert.equal(result.status, "INCOMPLETE");
  assert.equal(result.candidateModelSpec, null);
  assert.ok(result.missing.some((item) => item.subject === "material.youngsModulus"));
});

test("complete requirement returns a typed PR21 candidate", async () => {
  const result = await runFemRequirementComplete(process.cwd(), completeBeamDraft());

  assert.equal(result.status, "COMPLETE");
  assert.notEqual(result.candidateModelSpec, null);
  assert.equal(result.candidateModelSpec?.schemaVersion, "1.0");
  assert.equal(result.modelSpecValidation?.status, "VALID");
  assert.equal(typeof result.modelSpecFingerprint, "string");
});
