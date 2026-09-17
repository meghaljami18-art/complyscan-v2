export type Role = "COMPLIANCE_ANALYST" | "LEGAL_REVIEWER" | "VIEWER" | "ADMIN";
export type RuleStatus = "PASS" | "FAIL" | "REVIEW" | "NOT_APPLICABLE";
export type Decision = "CONFIRMED" | "DISMISSED" | "MORE_EVIDENCE" | "ESCALATED";
export type QualityStatus = "GOOD" | "FAIR" | "POOR";
export type TriState = "TRUE" | "FALSE" | "UNKNOWN";

export interface UserIdentity {
  email: string;
  role: Role;
  name: string;
}

export interface InspectionContext {
  package_context: "RETAIL" | "ECOMMERCE" | "WHOLESALE" | "EXPORT";
  commodity_type: string;
  date_required: TriState;
  medical_device: TriState;
}

export interface QualityReason {
  code: string;
  message: string;
}

export interface QualitySummary {
  status: QualityStatus;
  score: number;
  policy_version: "QUALITY_BROWSER_V1";
  reasons: QualityReason[];
}

export interface Candidate {
  value: string;
  qualifier?: string | null;
  confidence: number;
  evidence_excerpt: string;
  image_index: number;
  method: string;
}

export interface Extraction {
  product: {
    name?: string | null;
    brand?: string | null;
    commodity_type?: string | null;
    medical_device: TriState;
  };
  coverage: {
    sides: string[];
    mandatory_panel_visible: "YES" | "NO" | "UNCERTAIN";
    notes: string;
  };
  mrp: Candidate[];
  net_quantity: Candidate[];
  responsible_entity: Candidate[];
  address: Candidate[];
  date: Candidate[];
  consumer_care: Candidate[];
  visual: {
    legibility: "GOOD" | "FAIR" | "POOR" | "UNKNOWN";
    contrast: "ADEQUATE" | "LOW" | "UNKNOWN";
    principal_panel_visible: "YES" | "NO" | "UNCERTAIN";
    exact_font_size_verifiable: false;
    notes: string;
  };
  raw_text_by_image: string[];
}

export interface EvidenceItem {
  id: string;
  field: string;
  value?: string | null;
  excerpt: string;
  confidence?: number | null;
  image_index?: number | null;
  method: string;
}

export interface RuleResult {
  rule_id: string;
  title: string;
  status: RuleStatus;
  ui_label: string;
  legal_output: string;
  source: string;
  verification_mode: string;
  explanation: string;
  evidence: EvidenceItem[];
  next_action: string;
}

export interface Assessment {
  ruleset_id: string;
  ruleset_version: string;
  overall_status: RuleStatus;
  overall_label: string;
  results: RuleResult[];
  counts: Record<string, number>;
  guardrails: string[];
}

export interface ReviewRecord {
  decision: Decision;
  reason: string;
  actor_email?: string;
  actor_role?: Role;
  decided_at?: string;
}

export interface InspectionRecord {
  id: string;
  status: "DRAFT" | "ANALYZED" | "IN_REVIEW" | "REVIEW_COMPLETE";
  created_at: string;
  updated_at: string;
  created_by: string;
  context: InspectionContext;
  image_names: string[];
  image_urls: string[];
  quality: QualitySummary;
  extraction?: Extraction | null;
  assessment?: Assessment | null;
  provider?: string | null;
  model?: string | null;
  review_decisions: Record<string, ReviewRecord | Decision | unknown>;
}

export interface HealthResponse {
  status?: string;
  service?: string;
  environment?: string;
  vision?: {
    provider?: string;
    configured?: boolean;
    model?: string;
  };
  storage?: {
    provider?: string;
    direct_upload?: boolean;
    upload_intent_endpoint?: string;
  };
  database?: { configured?: boolean; adapter?: string };
  ruleset?: { id?: string; version?: string };
  gemini_configured?: boolean;
  vision_provider?: string;
  ruleset_version?: string;
}

export interface ImageQueueItem {
  id: string;
  file: File;
  preview: string;
  quality: QualitySummary;
  width: number;
  height: number;
  megapixels: number;
}

export interface RuleDefinition {
  id: string;
  title: string;
  source: string;
  verificationMode: string;
  purpose: string;
}
