import type { Role, RuleDefinition } from "./types";

export const RULESET_VERSION = "LMPC_2026_08_26";

export const RULES: RuleDefinition[] = [
  {
    id: "LMPC-MVP-001",
    title: "MRP / Retail Sale Price",
    source: "Rule 6 + applicable sticker provisions",
    verificationMode: "IMAGE_ONLY / IMAGE_ASSISTED",
    purpose: "Verify required MRP presence and readable form.",
  },
  {
    id: "LMPC-MVP-002",
    title: "Net Quantity + Unit",
    source: "Rules 11–13 + Fourth Schedule where applicable",
    verificationMode: "IMAGE_ONLY / IMAGE_ASSISTED",
    purpose: "Verify declared quantity and unit or basis; not physical quantity accuracy.",
  },
  {
    id: "LMPC-MVP-003",
    title: "Manufacturer / Packer / Importer",
    source: "Rule 6 + Rule 10",
    verificationMode: "IMAGE_ONLY / IMAGE_ASSISTED / EXTERNAL_DATA",
    purpose: "Verify responsible entity identity and a readable address.",
  },
  {
    id: "LMPC-MVP-004",
    title: "Applicable Date Declaration",
    source: "Rule 6 + commodity applicability",
    verificationMode: "IMAGE_ONLY / IMAGE_ASSISTED",
    purpose: "Verify a date only when the package context establishes that it is required.",
  },
  {
    id: "LMPC-MVP-005",
    title: "Placement / Legibility",
    source: "Rules 7–9; MDR route where applicable",
    verificationMode: "IMAGE_ASSISTED",
    purpose: "Screen observable readability predicates; exact font height is not claimed.",
  },
];

export const ROLE_LABELS: Record<Role, string> = {
  COMPLIANCE_ANALYST: "Compliance analyst",
  LEGAL_REVIEWER: "Legal reviewer",
  VIEWER: "Read-only auditor",
  ADMIN: "Administrator",
};

export const ROLE_DESCRIPTIONS: Record<Role, string> = {
  COMPLIANCE_ANALYST: "Capture evidence, run screening checks, and prepare a review record.",
  LEGAL_REVIEWER: "Review every applicable check and record a reasoned disposition.",
  VIEWER: "Inspect evidence, decisions, history, and reports without changing records.",
  ADMIN: "View service controls, role boundaries, ruleset health, and all review tools.",
};

export const WORKFLOW = ["Capture", "Quality", "Read", "Applicability", "Check", "Review", "Report"] as const;
