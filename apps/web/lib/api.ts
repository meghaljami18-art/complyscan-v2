import { upload } from "@vercel/blob/client";

import type {
  Candidate,
  Decision,
  HealthResponse,
  InspectionContext,
  InspectionRecord,
  QualitySummary,
  Role,
} from "./types";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(message: string, status: number, code = "REQUEST_FAILED") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function demoToken(email: string, role: Role): string {
  const safeSubject = email.toLowerCase().replace(/[^a-z0-9@._-]/g, "");
  return `demo:${safeSubject}:${role}`;
}

function nestedMessage(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && "message" in value && typeof (value as { message?: unknown }).message === "string") {
    return (value as { message: string }).message;
  }
  return null;
}

function getMessage(data: unknown, status: number): string {
  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;
    const detail = nestedMessage(record.detail);
    const error = nestedMessage(record.error);
    if (detail) return detail;
    if (error) return error;
    if (typeof record.message === "string") return record.message;
    if (Array.isArray(record.detail)) {
      return record.detail.map((item) => (typeof item === "object" && item && "msg" in item ? String(item.msg) : String(item))).join("; ");
    }
  }
  return `Request failed (${status}).`;
}

function getCode(data: unknown): string {
  if (!data || typeof data !== "object") return "REQUEST_FAILED";
  const record = data as Record<string, unknown>;
  if (typeof record.code === "string") return record.code;
  for (const value of [record.error, record.detail]) {
    if (value && typeof value === "object" && "code" in value && typeof (value as { code?: unknown }).code === "string") {
      return (value as { code: string }).code;
    }
  }
  return "REQUEST_FAILED";
}

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "");

export async function apiRequest<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const url = path.startsWith("/api/") && API_BASE ? `${API_BASE}${path}` : path;
  const response = await fetch(url, {
    ...init,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers || {}),
    },
  });
  const data = (await response.json().catch(() => null)) as T | null;
  if (!response.ok) {
    throw new ApiError(getMessage(data, response.status), response.status, getCode(data));
  }
  return (data ?? ({} as T)) as T;
}

type ApiCandidate = Omit<Candidate, "evidence_excerpt"> & { evidence?: string; evidence_excerpt?: string };
type ApiImage = { file_name?: string; download_url?: string | null };
type ApiExtraction = {
  product?: InspectionRecord["extraction"] extends infer E ? E extends { product: infer P } ? P : never : never;
  coverage?: { package_sides_visible?: string[]; mandatory_declaration_panel_visible?: "YES" | "NO" | "UNCERTAIN"; coverage_notes?: string[] };
  fields?: Record<string, ApiCandidate[]>;
  visual?: { overall_legibility?: "CLEAR" | "PARTIAL" | "POOR" | "UNCERTAIN"; contrast?: "ADEQUATE" | "LOW" | "UNCERTAIN"; principal_display_panel_visible?: "YES" | "NO" | "UNCERTAIN"; exact_font_size_verifiable?: false; notes?: string[] };
  raw_text_by_image?: Array<{ image_index?: number; text?: string }>;
};
type ApiInspection = Omit<InspectionRecord, "image_names" | "image_urls" | "extraction"> & {
  images?: ApiImage[];
  image_names?: string[];
  image_urls?: string[];
  extraction?: ApiExtraction | InspectionRecord["extraction"] | null;
};

function normalizeCandidate(candidate: ApiCandidate): Candidate {
  return { ...candidate, evidence_excerpt: candidate.evidence_excerpt || candidate.evidence || candidate.value };
}

function normalizeInspection(input: ApiInspection): InspectionRecord {
  const raw = input.extraction as ApiExtraction | null | undefined;
  const fields = raw?.fields;
  const alreadyFlat = raw && !fields && "mrp" in raw;
  const extraction: InspectionRecord["extraction"] = !raw ? null : alreadyFlat ? raw as unknown as InspectionRecord["extraction"] : ({
    product: raw.product || { medical_device: "UNKNOWN" },
    coverage: {
      sides: raw.coverage?.package_sides_visible || [],
      mandatory_panel_visible: raw.coverage?.mandatory_declaration_panel_visible || "UNCERTAIN",
      notes: (raw.coverage?.coverage_notes || []).join(" "),
    },
    mrp: (fields?.mrp || []).map(normalizeCandidate),
    net_quantity: (fields?.net_quantity || []).map(normalizeCandidate),
    responsible_entity: (fields?.responsible_entity || []).map(normalizeCandidate),
    address: (fields?.address || []).map(normalizeCandidate),
    date: (fields?.date || []).map(normalizeCandidate),
    consumer_care: (fields?.consumer_care || []).map(normalizeCandidate),
    visual: {
      legibility: raw.visual?.overall_legibility === "CLEAR" ? "GOOD" : raw.visual?.overall_legibility === "PARTIAL" ? "FAIR" : raw.visual?.overall_legibility === "POOR" ? "POOR" : "UNKNOWN",
      contrast: raw.visual?.contrast === "UNCERTAIN" ? "UNKNOWN" : raw.visual?.contrast || "UNKNOWN",
      principal_panel_visible: raw.visual?.principal_display_panel_visible || "UNCERTAIN",
      exact_font_size_verifiable: false as const,
      notes: (raw.visual?.notes || []).join(" "),
    },
    raw_text_by_image: (raw.raw_text_by_image || []).sort((a, b) => (a.image_index || 0) - (b.image_index || 0)).map((item) => item.text || ""),
  } as InspectionRecord["extraction"]);
  const images = input.images || [];
  const assessment = input.assessment ? {
    ...input.assessment,
    results: input.assessment.results.map((result) => ({
      ...result,
      evidence: result.evidence.map((item) => ({ ...item, field: (item as { field?: string }).field || result.title })),
    })),
  } : input.assessment;
  return {
    ...(input as unknown as InspectionRecord),
    image_names: input.image_names || images.map((item) => item.file_name || "package-image"),
    image_urls: input.image_urls || images.map((item) => item.download_url || "").filter(Boolean),
    extraction,
    assessment,
  };
}

export async function getHealth(token: string): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/api/health", token);
}

export async function listInspections(token: string): Promise<InspectionRecord[]> {
  const data = await apiRequest<ApiInspection[] | { inspections: ApiInspection[] }>("/api/inspections", token);
  return (Array.isArray(data) ? data : data.inspections || []).map(normalizeInspection);
}

export async function createInspection(
  token: string,
  context: InspectionContext,
  imageNames: string[],
  quality: QualitySummary,
): Promise<InspectionRecord> {
  const data = await apiRequest<ApiInspection | { inspection: ApiInspection }>("/api/inspections", token, {
    method: "POST",
    body: JSON.stringify({ context, image_names: imageNames, quality }),
  });
  return normalizeInspection("inspection" in data ? data.inspection : data);
}

export interface AnalyzeImage {
  name: string;
  mime_type: "image/jpeg";
  data: string;
  quality: QualitySummary;
}

export async function analyzeInspection(
  token: string,
  inspectionId: string,
  payload: {
    images: AnalyzeImage[];
    image_urls: string[];
    context: InspectionContext;
    requested_provider: "configured" | "fixture";
  },
): Promise<InspectionRecord> {
  const data = await apiRequest<ApiInspection | { inspection: ApiInspection }>(
    `/api/inspections/${encodeURIComponent(inspectionId)}/analyze`,
    token,
    { method: "POST", body: JSON.stringify(payload) },
  );
  return normalizeInspection("inspection" in data ? data.inspection : data);
}

export async function reviewRule(
  token: string,
  inspectionId: string,
  ruleId: string,
  decision: Decision,
  reason: string,
): Promise<InspectionRecord> {
  const data = await apiRequest<ApiInspection | { inspection: ApiInspection }>(
    `/api/inspections/${encodeURIComponent(inspectionId)}/reviews`,
    token,
    { method: "POST", body: JSON.stringify({ rule_id: ruleId, decision, reason }) },
  );
  return normalizeInspection("inspection" in data ? data.inspection : data);
}

export async function getReport(token: string, inspectionId: string): Promise<unknown> {
  return apiRequest(`/api/inspections/${encodeURIComponent(inspectionId)}/report.json`, token);
}

export async function getAuditEvents(token: string): Promise<unknown[]> {
  const data = await apiRequest<unknown[] | { events: unknown[] }>("/api/audit-events", token);
  return Array.isArray(data) ? data : data.events || [];
}

/**
 * Uploads image bytes directly from the browser to a private Vercel Blob store.
 * The Next.js token route authorizes each short-lived upload; the permanent Blob
 * credential never enters the browser bundle or the FastAPI request body.
 */
export async function directUploadImages(token: string, blobs: Blob[], names: string[]): Promise<string[]> {
  const completed = await Promise.all(blobs.map(async (blob, index) => {
    const safeName = names[index].replace(/[^A-Za-z0-9._-]/g, "_") || `image-${index + 1}.jpg`;
    const pathname = `complyscan/${crypto.randomUUID()}/${safeName.replace(/\.[^.]+$/, "")}.jpg`;
    const stored = await upload(pathname, blob, {
      access: "private",
      handleUploadUrl: "/api/blob-upload",
      headers: { Authorization: `Bearer ${token}` },
      contentType: "image/jpeg",
      multipart: false,
    });
    const downloadUrl = stored.downloadUrl || stored.url;
    if (!downloadUrl.startsWith("https://")) throw new Error("Object storage did not return an HTTPS evidence URL.");
    await apiRequest("/api/storage/objects", token, {
      method: "POST",
      body: JSON.stringify({
        object_key: stored.pathname,
        file_name: safeName,
        content_type: "image/jpeg",
        size_bytes: blob.size,
        download_url: downloadUrl,
      }),
    });
    return downloadUrl;
  }));
  return completed;
}
