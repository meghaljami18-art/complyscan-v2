import test from "node:test";
import { strict as assert } from "node:assert";

import { classifyQuality } from "../lib/quality.ts";

test("accepts a sharp, well-lit capture", () => {
  assert.deepEqual(classifyQuality({ mean: 128, contrast: 48, detail: 39, megapixels: 2.4 }), {
    status: "GOOD",
    score: 0.97,
    policy_version: "QUALITY_BROWSER_V1",
    reasons: [],
  });
});

test("routes one concern to fair quality", () => {
  const result = classifyQuality({ mean: 128, contrast: 48, detail: 39, megapixels: 0.5 });
  assert.equal(result.status, "FAIR");
  assert.deepEqual(result.reasons.map((reason) => reason.code), ["LOW_RESOLUTION"]);
});

test("conservatively routes multiple concerns to poor quality", () => {
  const result = classifyQuality({ mean: 25, contrast: 18, detail: 12, megapixels: 0.2 });
  assert.equal(result.status, "POOR");
  assert.ok(result.score >= 0.05);
  assert.deepEqual(result.reasons.map((reason) => reason.code), [
    "DARK",
    "LOW_CONTRAST",
    "POSSIBLE_BLUR",
    "LOW_RESOLUTION",
  ]);
});
