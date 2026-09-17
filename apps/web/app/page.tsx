"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  analyzeInspection,
  createInspection,
  demoToken,
  directUploadImages,
  getAuditEvents,
  getHealth,
  getReport,
  listInspections,
  reviewRule,
} from "@/lib/api";
import { ROLE_DESCRIPTIONS, ROLE_LABELS, RULES, RULESET_VERSION, WORKFLOW } from "@/lib/constants";
import { aggregateQuality, blobToBase64, compressImage, measureImage } from "@/lib/quality";
import type {
  Candidate,
  Decision,
  HealthResponse,
  ImageQueueItem,
  InspectionContext,
  InspectionRecord,
  Role,
  RuleResult,
  RuleStatus,
  UserIdentity,
} from "@/lib/types";

type View = "dashboard" | "new" | "review" | "history" | "rules" | "admin";
type Toast = { id: number; message: string; kind: "success" | "error" };

const DEFAULT_CONTEXT: InspectionContext = {
  package_context: "RETAIL",
  commodity_type: "",
  date_required: "UNKNOWN",
  medical_device: "UNKNOWN",
};

const PAGE_META: Record<View, [string, string]> = {
  dashboard: ["ENFORCEMENT WORKSPACE", "Compliance overview"],
  new: ["NEW INSPECTION", "Capture package evidence"],
  review: ["EVIDENCE REVIEW", "Inspection workspace"],
  history: ["SCREENING REPOSITORY", "Inspection history"],
  rules: ["VERSIONED RULESET", "MVP rule register"],
  admin: ["ADMINISTRATION", "Service & access overview"],
};

const FIELD_DEFINITIONS: Array<[string, keyof NonNullable<InspectionRecord["extraction"]>]> = [
  ["MRP", "mrp"],
  ["Net quantity", "net_quantity"],
  ["Responsible entity", "responsible_entity"],
  ["Address", "address"],
  ["Applicable date", "date"],
  ["Consumer care", "consumer_care"],
];

const REVIEW_DECISIONS: Array<[Decision, string]> = [
  ["CONFIRMED", "Confirm result"],
  ["DISMISSED", "Dismiss"],
  ["MORE_EVIDENCE", "Request evidence"],
  ["ESCALATED", "Escalate"],
];

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "—";
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function statusLabel(status?: RuleStatus | string | null) {
  const labels: Record<string, string> = {
    PASS: "Passed",
    FAIL: "Potential issue",
    REVIEW: "Needs review",
    NOT_APPLICABLE: "Not applicable",
  };
  return labels[status || ""] || "Needs review";
}

function statusClass(status?: RuleStatus | string | null) {
  return `status status-${String(status || "REVIEW").toLowerCase().replaceAll("_", "-")}`;
}

function reviewDecisionValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && "decision" in value) return String((value as { decision: unknown }).decision);
  return "";
}

function downloadJson(value: unknown, filename: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function LoginScreen({ onLogin }: { onLogin: (user: UserIdentity, token: string) => void }) {
  const [email, setEmail] = useState("judge@complyscan.demo");
  const [selectedRole, setSelectedRole] = useState<Role>("COMPLIANCE_ANALYST");

  return (
    <main className="login-shell">
      <section className="login-story" aria-labelledby="login-title">
        <a className="brand brand-on-dark" href="#login-title" aria-label="COMPLYSCAN home">
          <span className="brand-mark">C</span>
          <span>COMPLYSCAN<small>Evidence-first screening</small></span>
        </a>
        <div className="login-copy">
          <p className="eyebrow mint-text">LEGAL METROLOGY · PACKAGED COMMODITIES</p>
          <h1 id="login-title">From package image to traceable compliance review.</h1>
          <p>Capture evidence, explain applicability, apply five versioned checks, and keep the human reviewer in control.</p>
        </div>
        <ol className="login-flow" aria-label="COMPLYSCAN workflow">
          {WORKFLOW.map((step, index) => <li key={step}><span>0{index + 1}</span>{step}</li>)}
        </ol>
        <p className="legal-note">Decision support only. Automated screening is not a final legal or enforcement determination.</p>
      </section>

      <section className="login-panel" aria-labelledby="role-title">
        <div className="login-form-wrap">
          <p className="eyebrow">SECURE DEMO WORKSPACE</p>
          <h2 id="role-title">Choose a demo role</h2>
          <p className="muted">Role boundaries are enforced again by the FastAPI service. Demo identity is disabled in production.</p>
          <label className="field-label" htmlFor="demo-email">Demo email</label>
          <input id="demo-email" className="text-input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          <div className="role-grid" role="radiogroup" aria-label="Demo role">
            {(Object.keys(ROLE_LABELS) as Role[]).map((role) => (
              <button
                type="button"
                role="radio"
                aria-checked={selectedRole === role}
                className={`role-card ${selectedRole === role ? "is-selected" : ""}`}
                key={role}
                onClick={() => setSelectedRole(role)}
              >
                <span className="role-icon">{role === "ADMIN" ? "A" : role === "LEGAL_REVIEWER" ? "R" : role === "VIEWER" ? "V" : "I"}</span>
                <strong>{ROLE_LABELS[role]}</strong>
                <small>{ROLE_DESCRIPTIONS[role]}</small>
              </button>
            ))}
          </div>
          <button
            className="button button-primary button-wide"
            onClick={() => {
              const safeEmail = email.trim() || "judge@complyscan.demo";
              onLogin({ email: safeEmail, role: selectedRole, name: ROLE_LABELS[selectedRole] }, demoToken(safeEmail, selectedRole));
            }}
          >
            Enter evidence workspace <span aria-hidden="true">→</span>
          </button>
          <p className="secure-copy"><span aria-hidden="true">●</span> No Gemini key is requested, stored, or exposed in this browser.</p>
        </div>
      </section>
    </main>
  );
}

function Badge({ status, children }: { status?: string | null; children?: React.ReactNode }) {
  return <span className={statusClass(status)}><span className="status-dot" />{children || statusLabel(status)}</span>;
}

function EmptyState({ title, body, action }: { title: string; body: string; action?: React.ReactNode }) {
  return <div className="empty-state"><span className="empty-icon" aria-hidden="true">◎</span><strong>{title}</strong><p>{body}</p>{action}</div>;
}

export default function Home() {
  const [user, setUser] = useState<UserIdentity | null>(null);
  const [token, setToken] = useState("");
  const [view, setView] = useState<View>("dashboard");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [serviceOnline, setServiceOnline] = useState(false);
  const [inspections, setInspections] = useState<InspectionRecord[]>([]);
  const [current, setCurrent] = useState<InspectionRecord | null>(null);
  const [files, setFiles] = useState<ImageQueueItem[]>([]);
  const [context, setContext] = useState<InspectionContext>(DEFAULT_CONTEXT);
  const [fixtureMode, setFixtureMode] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [progressIndex, setProgressIndex] = useState(0);
  const [selectedImage, setSelectedImage] = useState(0);
  const [openRules, setOpenRules] = useState<Set<string>>(new Set());
  const [reviewReasons, setReviewReasons] = useState<Record<string, string>>({});
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("ALL");
  const [auditEvents, setAuditEvents] = useState<unknown[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [navOpen, setNavOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const notify = useCallback((message: string, kind: Toast["kind"] = "success") => {
    const id = Date.now() + Math.random();
    setToasts((existing) => [...existing, { id, message, kind }]);
    window.setTimeout(() => setToasts((existing) => existing.filter((item) => item.id !== id)), 4400);
  }, []);

  const refreshData = useCallback(async (authToken: string) => {
    try {
      const [healthData, inspectionData] = await Promise.all([getHealth(authToken), listInspections(authToken)]);
      setHealth(healthData);
      setInspections(inspectionData);
      setServiceOnline(true);
    } catch (error) {
      setServiceOnline(false);
      if (error instanceof ApiError && error.status === 401) notify("Demo authorization was rejected by this deployment.", "error");
    }
  }, [notify]);

  useEffect(() => {
    const savedToken = window.sessionStorage.getItem("complyscan.demo.token");
    const savedUser = window.sessionStorage.getItem("complyscan.demo.user");
    if (savedToken && savedUser) {
      try {
        const parsed = JSON.parse(savedUser) as UserIdentity;
        setToken(savedToken);
        setUser(parsed);
        void refreshData(savedToken);
      } catch {
        window.sessionStorage.removeItem("complyscan.demo.token");
        window.sessionStorage.removeItem("complyscan.demo.user");
      }
    }
  }, [refreshData]);

  useEffect(() => {
    if (!processing) return;
    const timer = window.setInterval(() => setProgressIndex((value) => Math.min(5, value + 1)), 1400);
    return () => window.clearInterval(timer);
  }, [processing]);

  const login = (identity: UserIdentity, authToken: string) => {
    window.sessionStorage.setItem("complyscan.demo.token", authToken);
    window.sessionStorage.setItem("complyscan.demo.user", JSON.stringify(identity));
    setUser(identity);
    setToken(authToken);
    setView("dashboard");
    void refreshData(authToken);
  };

  const logout = () => {
    window.sessionStorage.removeItem("complyscan.demo.token");
    window.sessionStorage.removeItem("complyscan.demo.user");
    files.forEach((item) => URL.revokeObjectURL(item.preview));
    setFiles([]);
    setCurrent(null);
    setUser(null);
    setToken("");
  };

  const navigate = (next: View) => {
    if (next === "admin" && user?.role !== "ADMIN") {
      notify("Administrator access is required.", "error");
      return;
    }
    if (next === "review" && !current) next = "new";
    setView(next);
    setNavOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const resetInspection = () => {
    files.forEach((item) => URL.revokeObjectURL(item.preview));
    setFiles([]);
    setCurrent(null);
    setContext(DEFAULT_CONTEXT);
    setFixtureMode(false);
    setSelectedImage(0);
    setOpenRules(new Set());
    setReviewReasons({});
    setView("new");
  };

  const addFiles = async (incoming: File[]) => {
    if (user?.role === "VIEWER") return notify("Read-only users cannot add evidence.", "error");
    const imageFiles = incoming.filter((file) => ["image/jpeg", "image/png", "image/webp"].includes(file.type));
    if (!imageFiles.length) return notify("Choose JPG, PNG, or WebP package images.", "error");
    const existingKeys = new Set(files.map((item) => `${item.file.name}:${item.file.size}:${item.file.lastModified}`));
    const unique = imageFiles.filter((file) => !existingKeys.has(`${file.name}:${file.size}:${file.lastModified}`));
    const available = Math.max(0, 6 - files.length);
    if (unique.length > available) notify(`Only ${available} more image${available === 1 ? "" : "s"} can be added.`, "error");
    const prepared: ImageQueueItem[] = [];
    for (const file of unique.slice(0, available)) {
      try {
        const measured = await measureImage(file);
        prepared.push({ id: crypto.randomUUID(), file, preview: URL.createObjectURL(file), ...measured });
      } catch (error) {
        notify(error instanceof Error ? error.message : "Image quality preflight failed.", "error");
      }
    }
    setFiles((existing) => [...existing, ...prepared]);
    setFixtureMode(false);
  };

  const loadSample = async (kind: "complete" | "coverage") => {
    const path = kind === "complete" ? "/samples/cinthol-label.jpg" : "/samples/zebronics-front.jpg";
    const name = kind === "complete" ? "cinthol-label.jpg" : "zebronics-front.jpg";
    try {
      const response = await fetch(path);
      if (!response.ok) throw new Error("Sample image could not be loaded.");
      const blob = await response.blob();
      const sample = new File([blob], name, { type: "image/jpeg", lastModified: Date.now() });
      files.forEach((item) => URL.revokeObjectURL(item.preview));
      setFiles([]);
      const measured = await measureImage(sample);
      setFiles([{ id: crypto.randomUUID(), file: sample, preview: URL.createObjectURL(sample), ...measured }]);
      setContext(kind === "complete"
        ? { package_context: "RETAIL", commodity_type: "Talcum powder", date_required: "TRUE", medical_device: "FALSE" }
        : { package_context: "RETAIL", commodity_type: "Wireless mouse", date_required: "UNKNOWN", medical_device: "FALSE" });
      setFixtureMode(true);
      notify(`${kind === "complete" ? "Complete-label" : "Front-view-only"} evidence sample loaded.`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Sample could not be loaded.", "error");
    }
  };

  const removeImage = (id: string) => {
    const match = files.find((item) => item.id === id);
    if (match) URL.revokeObjectURL(match.preview);
    setFiles((items) => items.filter((item) => item.id !== id));
    setFixtureMode(false);
  };

  const runAnalysis = async () => {
    if (!files.length || !user) return;
    if (!context.commodity_type.trim()) return notify("Describe the commodity before analysis so applicability is traceable.", "error");
    setProcessing(true);
    setProgressIndex(0);
    try {
      const quality = aggregateQuality(files);
      const draft = await createInspection(token, { ...context, commodity_type: context.commodity_type.trim() }, files.map((item) => item.file.name), quality);
      setProgressIndex(1);
      const compressed: Blob[] = [];
      for (const item of files) compressed.push(await compressImage(item.file));
      setProgressIndex(2);

      let imageUrls: string[] = [];
      let inlineImages: Array<{ name: string; mime_type: "image/jpeg"; data: string; quality: typeof quality }> = [];
      const directEnabled = Boolean(health?.storage?.direct_upload || process.env.NEXT_PUBLIC_DIRECT_UPLOADS === "true");
      if (directEnabled && !fixtureMode) {
        try {
          imageUrls = await directUploadImages(token, compressed, files.map((item) => item.file.name));
        } catch (error) {
          const totalBytes = compressed.reduce((sum, blob) => sum + blob.size, 0);
          if (totalBytes > 2_800_000) throw error;
          notify("Direct object upload was unavailable; using the bounded inline preview path.", "error");
        }
      }
      if (!imageUrls.length) {
        const totalBytes = compressed.reduce((sum, blob) => sum + blob.size, 0);
        if (totalBytes > 2_800_000) throw new Error("Compressed evidence exceeds the local inline limit. Configure direct object uploads or reduce the images.");
        inlineImages = await Promise.all(compressed.map(async (blob, index) => ({
          name: files[index].file.name,
          mime_type: "image/jpeg" as const,
          data: await blobToBase64(blob),
          quality: files[index].quality,
        })));
      }
      setProgressIndex(3);
      const analyzed = await analyzeInspection(token, draft.id, {
        images: inlineImages,
        image_urls: imageUrls,
        context: { ...context, commodity_type: context.commodity_type.trim() },
        requested_provider: fixtureMode ? "fixture" : "configured",
      });
      setProgressIndex(5);
      setCurrent(analyzed);
      setInspections((items) => [analyzed, ...items.filter((item) => item.id !== analyzed.id)]);
      setSelectedImage(0);
      setOpenRules(new Set());
      setView("review");
      notify("Screening completed. Review each applicable result and its evidence.");
    } catch (error) {
      notify(error instanceof Error ? error.message : "Analysis failed. The draft remains safe to retry.", "error");
    } finally {
      setProcessing(false);
    }
  };

  const submitDecision = async (rule: RuleResult, decision: Decision) => {
    if (!current || !user || !["LEGAL_REVIEWER", "ADMIN"].includes(user.role)) return;
    const reason = (reviewReasons[rule.rule_id] || "").trim();
    if (reason.length < 3) return notify("Add a short audit reason before recording a reviewer decision.", "error");
    try {
      const updated = await reviewRule(token, current.id, rule.rule_id, decision, reason);
      setCurrent(updated);
      setInspections((items) => items.map((item) => item.id === updated.id ? updated : item));
      setOpenRules((open) => new Set(open).add(rule.rule_id));
      notify(`${decision.replaceAll("_", " ").toLowerCase()} recorded with an audit reason.`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Reviewer decision could not be saved.", "error");
    }
  };

  const exportCurrent = async () => {
    if (!current) return;
    try {
      const report = serviceOnline ? await getReport(token, current.id) : current;
      downloadJson(report, `${current.id}-editable-report.json`);
      notify("Editable JSON report exported.");
    } catch {
      downloadJson(current, `${current.id}-editable-report.json`);
      notify("API report was unavailable; the current evidence record was exported.", "error");
    }
  };

  const openInspection = (record: InspectionRecord) => {
    setCurrent(record);
    setSelectedImage(0);
    setOpenRules(new Set());
    setView("review");
  };

  const loadAudit = async () => {
    try { setAuditEvents(await getAuditEvents(token)); }
    catch (error) { notify(error instanceof Error ? error.message : "Audit events are unavailable.", "error"); }
  };

  const metrics = useMemo(() => {
    const counts = inspections.reduce<Record<string, number>>((result, inspection) => {
      const status = inspection.assessment?.overall_status || "REVIEW";
      result[status] = (result[status] || 0) + 1;
      return result;
    }, {});
    return [
      ["TOTAL INSPECTIONS", inspections.length, "Traceable screening records", "metric-blue"],
      ["PASSED", counts.PASS || 0, "All selected MVP checks passed", "metric-green"],
      ["NEEDS REVIEW", counts.REVIEW || 0, "Uncertainty or applicability routing", "metric-amber"],
      ["POTENTIAL ISSUES", counts.FAIL || 0, "Not a final legal determination", "metric-coral"],
    ] as const;
  }, [inspections]);

  const filteredInspections = useMemo(() => inspections.filter((inspection) => {
    const product = inspection.extraction?.product;
    const haystack = `${inspection.id} ${product?.name || ""} ${product?.brand || ""} ${inspection.context.commodity_type}`.toLowerCase();
    const status = inspection.assessment?.overall_status || "REVIEW";
    return haystack.includes(search.toLowerCase()) && (filter === "ALL" || status === filter);
  }), [filter, inspections, search]);

  if (!user) return <LoginScreen onLogin={login} />;

  const [eyebrow, title] = PAGE_META[view];
  const reviewer = ["LEGAL_REVIEWER", "ADMIN"].includes(user.role);

  return (
    <div className="app-shell">
      <aside className={`sidebar ${navOpen ? "is-open" : ""}`}>
        <div className="sidebar-top">
          <a className="brand brand-on-dark" href="#dashboard" onClick={(event) => { event.preventDefault(); navigate("dashboard"); }}>
            <span className="brand-mark">C</span><span>COMPLYSCAN<small>Evidence-first screening</small></span>
          </a>
          <button className="mobile-close" onClick={() => setNavOpen(false)} aria-label="Close navigation">×</button>
        </div>
        <nav aria-label="Workspace navigation">
          <button className={view === "dashboard" ? "is-active" : ""} onClick={() => navigate("dashboard")}><span>⌂</span>Overview</button>
          <button className={["new", "review"].includes(view) ? "is-active" : ""} onClick={resetInspection}><span>＋</span>New inspection</button>
          <button className={view === "history" ? "is-active" : ""} onClick={() => navigate("history")}><span>▤</span>History</button>
          <button className={view === "rules" ? "is-active" : ""} onClick={() => navigate("rules")}><span>§</span>Rule register</button>
          {user.role === "ADMIN" && <button className={view === "admin" ? "is-active" : ""} onClick={() => navigate("admin")}><span>⚙</span>Admin</button>}
        </nav>
        <div className="ruleset-chip"><span className="pulse-dot" /><span><strong>5-rule MVP</strong><small>{health?.ruleset?.version || health?.ruleset_version || RULESET_VERSION}</small></span></div>
        <div className="sidebar-foot">
          <span className="role-pill">{ROLE_LABELS[user.role]}</span>
          <p>{ROLE_DESCRIPTIONS[user.role]}</p>
          <button onClick={logout}>Sign out</button>
        </div>
      </aside>
      {navOpen && <button className="nav-scrim" aria-label="Close navigation" onClick={() => setNavOpen(false)} />}

      <main className="main-area">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setNavOpen(true)} aria-label="Open navigation">☰</button>
          <div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1></div>
          <div className="topbar-actions">
            <span className={`service-state ${serviceOnline ? "online" : "offline"}`}><i />{serviceOnline ? `Service online · ${health?.vision?.provider || health?.vision_provider || "ready"}` : "Service offline"}</span>
            <span className="user-chip"><span>{user.name.slice(0, 1)}</span><strong>{user.name}<small>{user.email}</small></strong></span>
          </div>
        </header>

        {view === "dashboard" && (
          <div className="page-content dashboard-page">
            <section className="hero-panel">
              <div className="hero-copy">
                <p className="eyebrow mint-text">EVIDENCE → APPLICABILITY → REVIEW</p>
                <h2>Inspect what is visible.<br />Explain every result.</h2>
                <p>AI reads label evidence. A versioned engine checks only what applies. Authorized reviewers keep the final say.</p>
                <div className="button-row">
                  {user.role !== "VIEWER" && <button className="button button-primary" onClick={resetInspection}>Start inspection <span>→</span></button>}
                  <button className="button button-dark-ghost" onClick={() => { resetInspection(); void loadSample("complete"); }}>Open judge demo</button>
                </div>
              </div>
              <div className="hero-visual" aria-label="Evidence chain preview">
                <div className="mini-image"><img src="/samples/cinthol-label.jpg" alt="Sample declaration label" /></div>
                <div className="evidence-chain">
                  <span><i>1</i><small>VISIBLE EVIDENCE</small><strong>MRP ₹199 · 96%</strong></span>
                  <span><i>2</i><small>APPLICABLE CHECK</small><strong>MRP declaration</strong></span>
                  <span><i>3</i><small>HUMAN ACTION</small><strong>Confirm evidence</strong></span>
                </div>
              </div>
            </section>

            <section className="metric-grid" aria-label="Inspection metrics">
              {metrics.map(([label, value, note, color]) => <article className={`metric ${color}`} key={label}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>)}
            </section>

            <section className="content-card recent-card">
              <header className="section-heading"><div><p className="eyebrow">RECENT WORK</p><h2>Inspections requiring attention</h2></div><button className="text-button" onClick={() => navigate("history")}>View all records →</button></header>
              <InspectionTable rows={inspections.slice(0, 6)} onOpen={openInspection} />
            </section>
          </div>
        )}

        {view === "new" && (
          <div className="page-content new-page">
            <WorkflowRail current={files.length ? 1 : 0} />
            <section className="inspection-intro">
              <div><p className="eyebrow">CAPTURE REAL PACKAGE EVIDENCE</p><h2>Add clear views of every declaration panel</h2><p>Use the original package. Quality checks run in this browser before anything is sent for analysis.</p></div>
              <div className="sample-actions"><span>JUDGE DEMOS</span><button onClick={() => void loadSample("complete")}>Complete label</button><button onClick={() => void loadSample("coverage")}>Front view only</button></div>
            </section>

            <div className="capture-grid">
              <section className="content-card upload-card">
                <header className="card-heading"><div><p className="eyebrow">01 · PACKAGE EVIDENCE</p><h3>Product images</h3></div><span className="count-badge">{files.length} / 6</span></header>
                <button
                  className="dropzone"
                  onClick={() => fileInput.current?.click()}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => { event.preventDefault(); void addFiles([...event.dataTransfer.files]); }}
                  disabled={user.role === "VIEWER"}
                >
                  <span className="upload-icon">↑</span><strong>Drop package images here</strong><small>or click to choose JPG, PNG, or WebP · up to 6 images</small>
                </button>
                <input ref={fileInput} hidden type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => void addFiles([...(event.target.files || [])])} />
                {files.length > 0 && <div className="image-queue">{files.map((item, index) => (
                  <article className="image-card" key={item.id}>
                    <div><img src={item.preview} alt={`Package evidence ${index + 1}`} /><Badge status={item.quality.status === "GOOD" ? "PASS" : item.quality.status === "POOR" ? "FAIL" : "REVIEW"}>{item.quality.status}</Badge><button onClick={() => removeImage(item.id)} aria-label={`Remove ${item.file.name}`}>×</button></div>
                    <strong>{item.file.name}</strong><small>{item.megapixels.toFixed(1)} MP · {item.quality.reasons[0]?.message || "Capture usable"}</small>
                  </article>
                ))}</div>}
                {files.length > 0 && <QualityPanel files={files} />}
              </section>

              <section className="content-card context-card">
                <header className="card-heading"><div><p className="eyebrow">02 · APPLICABILITY INPUTS</p><h3>Package context</h3></div><span className="count-badge">REQUIRED</span></header>
                <p className="muted">These facts select checks. Inspectors never choose a legal ruleset manually.</p>
                <label className="field-label">Market route<select value={context.package_context} onChange={(event) => setContext({ ...context, package_context: event.target.value as InspectionContext["package_context"] })}><option value="RETAIL">Retail package</option><option value="ECOMMERCE">E-commerce listing/package</option><option value="WHOLESALE">Wholesale package</option><option value="EXPORT">Export package</option></select></label>
                <label className="field-label">Commodity type<input className="text-input" placeholder="e.g. talcum powder" value={context.commodity_type} onChange={(event) => setContext({ ...context, commodity_type: event.target.value })} /></label>
                <label className="field-label">Is a date declaration required?<select value={context.date_required} onChange={(event) => setContext({ ...context, date_required: event.target.value as InspectionContext["date_required"] })}><option value="UNKNOWN">Unknown — route to review</option><option value="TRUE">Yes</option><option value="FALSE">No</option></select></label>
                <label className="field-label">Medical device?<select value={context.medical_device} onChange={(event) => setContext({ ...context, medical_device: event.target.value as InspectionContext["medical_device"] })}><option value="UNKNOWN">Unknown — route to review</option><option value="TRUE">Yes — MDR route</option><option value="FALSE">No</option></select></label>
                <div className="why-box"><strong>Why were these checks selected?</strong><p>{context.package_context === "EXPORT" ? "Retail MRP and quantity predicates will be marked not applicable in the prototype export route." : "Retail declaration checks are selected."} {context.date_required === "UNKNOWN" ? "Date applicability remains unresolved and will require review." : context.date_required === "TRUE" ? "The date check is executable." : "The date check will be excluded."} {context.medical_device !== "FALSE" ? "Medical-device status requires explicit routing." : "The general packaged-commodity route is selected."}</p></div>
                <button className="button button-primary button-wide" disabled={!files.length || processing || user.role === "VIEWER"} onClick={() => void runAnalysis()}>{processing ? "Processing evidence…" : "Analyze package"}<span>→</span></button>
                <p className="secure-copy center"><span aria-hidden="true">●</span> Vision credentials stay server-side. Browser uploads use short-lived storage intents when configured.</p>
              </section>
            </div>
          </div>
        )}

        {processing && <ProcessingOverlay stage={progressIndex} />}

        {view === "review" && current && (
          <ReviewWorkspace
            inspection={current}
            previews={files.map((item) => item.preview)}
            selectedImage={selectedImage}
            onSelectImage={setSelectedImage}
            openRules={openRules}
            onToggleRule={(id) => setOpenRules((existing) => { const next = new Set(existing); if (next.has(id)) next.delete(id); else next.add(id); return next; })}
            reviewer={reviewer}
            reasons={reviewReasons}
            setReason={(id, reason) => setReviewReasons((items) => ({ ...items, [id]: reason }))}
            onDecision={submitDecision}
            onExport={() => void exportCurrent()}
            onPrint={() => window.print()}
          />
        )}

        {view === "history" && (
          <div className="page-content history-page">
            <section className="content-card">
              <header className="section-heading"><div><p className="eyebrow">TRACEABLE RECORDS</p><h2>Inspection repository</h2><p>Search by inspection ID, product, brand, or commodity.</p></div><span className="count-badge">{filteredInspections.length} RECORDS</span></header>
              <div className="filter-row"><input className="text-input" type="search" placeholder="Search inspections…" value={search} onChange={(event) => setSearch(event.target.value)} /><select value={filter} onChange={(event) => setFilter(event.target.value)}><option value="ALL">All statuses</option><option value="PASS">Passed</option><option value="REVIEW">Needs review</option><option value="FAIL">Potential issue</option><option value="NOT_APPLICABLE">Not applicable</option></select></div>
              <InspectionTable rows={filteredInspections} onOpen={openInspection} />
            </section>
          </div>
        )}

        {view === "rules" && (
          <div className="page-content rules-page">
            <section className="rules-intro"><div><p className="eyebrow">LEGAL BASELINE</p><h2>Five narrow, versioned checks</h2><p>Every result exposes its source, verification mode, evidence, and next action. Legal currency must be verified before production enforcement use.</p></div><span className="version-seal"><small>ACTIVE BASELINE</small>{health?.ruleset?.version || health?.ruleset_version || RULESET_VERSION}</span></section>
            <div className="rule-register">{RULES.map((rule, index) => <article className="register-card" key={rule.id}><header><Badge status="NEUTRAL">{rule.id}</Badge><span>0{index + 1}</span></header><h3>{rule.title}</h3><p>{rule.purpose}</p><dl><div><dt>Source</dt><dd>{rule.source}</dd></div><div><dt>Verification mode</dt><dd>{rule.verificationMode}</dd></div><div><dt>Possible screen output</dt><dd>Passed · Potential issue · Needs review · Not applicable</dd></div></dl></article>)}</div>
            <section className="guardrail-banner"><strong>Evidence-first guardrail</strong><p>Physical accuracy, exact font height, external registration, and authority judgement do not silently pass from a package photograph.</p></section>
          </div>
        )}

        {view === "admin" && user.role === "ADMIN" && (
          <div className="page-content admin-page">
            <section className="admin-hero"><div><p className="eyebrow">SYSTEM BOUNDARY</p><h2>Prototype controls without hidden authority</h2><p>Identity, vision credentials, rules, storage, and persistence remain server-owned.</p></div><button className="button button-secondary" onClick={() => void loadAudit()}>Refresh audit trail</button></section>
            <div className="admin-grid">
              <section className="content-card"><p className="eyebrow">SERVICE HEALTH</p><h3>{serviceOnline ? "Backend reachable" : "Backend unavailable"}</h3><dl className="admin-list"><div><dt>Vision provider</dt><dd>{health?.vision?.provider || health?.vision_provider || "Unknown"}</dd></div><div><dt>Vision credential</dt><dd>{health?.vision?.configured || health?.gemini_configured ? "Server configured" : "Fixture/demo only"}</dd></div><div><dt>Object storage</dt><dd>{health?.storage?.direct_upload ? "Direct browser upload enabled" : "Inline local preview path"}</dd></div><div><dt>Database</dt><dd>{health?.database?.adapter || (health?.database?.configured ? "Configured" : "In-memory demo")}</dd></div><div><dt>Ruleset</dt><dd>{health?.ruleset?.version || health?.ruleset_version || RULESET_VERSION}</dd></div></dl></section>
              <section className="content-card"><p className="eyebrow">ROLE BOUNDARIES</p><h3>Least-authority demo access</h3><div className="permission-list">{(Object.keys(ROLE_LABELS) as Role[]).map((role) => <div key={role}><span className="role-icon">{role[0]}</span><span><strong>{ROLE_LABELS[role]}</strong><small>{ROLE_DESCRIPTIONS[role]}</small></span></div>)}</div></section>
              <section className="content-card audit-card"><p className="eyebrow">AUDIT TRAIL</p><h3>Recent server events</h3>{auditEvents.length ? <pre>{JSON.stringify(auditEvents.slice(0, 12), null, 2)}</pre> : <EmptyState title="No audit events loaded" body="Refresh to retrieve the current server-authoritative trail." />}</section>
            </div>
          </div>
        )}
      </main>

      <div className="toast-region" aria-live="polite">{toasts.map((toast) => <div className={`toast ${toast.kind}`} key={toast.id}>{toast.message}</div>)}</div>
    </div>
  );
}

function WorkflowRail({ current }: { current: number }) {
  return <ol className="workflow-rail" aria-label="Inspection workflow">{WORKFLOW.map((step, index) => <li className={index < current ? "complete" : index === current ? "current" : ""} key={step}><span>{index < current ? "✓" : index + 1}</span><small>{step}</small></li>)}</ol>;
}

function QualityPanel({ files }: { files: ImageQueueItem[] }) {
  const summary = aggregateQuality(files);
  return <div className={`quality-panel quality-${summary.status.toLowerCase()}`}><div><Badge status={summary.status === "GOOD" ? "PASS" : summary.status === "POOR" ? "FAIL" : "REVIEW"}>{summary.status} QUALITY</Badge><strong>Browser preflight score {Math.round(summary.score * 100)}%</strong></div><p>{summary.reasons.length ? summary.reasons.map((reason) => reason.message).join(" ") : "Lighting, contrast, detail, and capture resolution passed the browser preflight."} This score measures image usability, not legal compliance.</p></div>;
}

function ProcessingOverlay({ stage }: { stage: number }) {
  const stages = [
    ["Securing draft record", "Creating a traceable inspection before analysis begins."],
    ["Checking image quality", "Using browser-derived lighting, contrast, detail, and resolution signals."],
    ["Preparing package evidence", "Compressing locally and selecting the configured object-upload path."],
    ["Reading visible declarations", "Server-side vision extracts only evidence supported by supplied views."],
    ["Applying applicability", "Package context selects and excludes deterministic checks."],
    ["Building review workspace", "Linking each screening result to evidence, source, and next action."],
  ];
  return <div className="processing-overlay" role="status" aria-live="polite"><div className="processing-card"><div className="spinner" /><p className="eyebrow">CAPTURE → QUALITY → READ → APPLICABILITY → CHECK</p><h2>{stages[stage]?.[0]}</h2><p>{stages[stage]?.[1]}</p><div className="progress-track"><i style={{ width: `${((stage + 1) / stages.length) * 100}%` }} /></div><ol>{stages.map(([title], index) => <li className={index < stage ? "complete" : index === stage ? "current" : ""} key={title}><span>{index < stage ? "✓" : index + 1}</span>{title}</li>)}</ol></div></div>;
}

function InspectionTable({ rows, onOpen }: { rows: InspectionRecord[]; onOpen: (record: InspectionRecord) => void }) {
  if (!rows.length) return <EmptyState title="No inspection records yet" body="Run a sample or capture a package to create the first traceable record." />;
  return <div className="table-scroll"><table><caption className="sr-only">COMPLYSCAN inspection records</caption><thead><tr><th>Product</th><th>Inspection</th><th>Status</th><th>Evidence</th><th>Updated</th><th><span className="sr-only">Action</span></th></tr></thead><tbody>{rows.map((row) => {
    const product = row.extraction?.product;
    return <tr key={row.id}><td><strong>{product?.name || row.context.commodity_type || "Unclassified package"}</strong><small>{product?.brand || "Brand not extracted"}</small></td><td><code>{row.id}</code><small>{row.status.replaceAll("_", " ")}</small></td><td><Badge status={row.assessment?.overall_status}>{statusLabel(row.assessment?.overall_status)}</Badge></td><td>{row.image_names?.length || 0} image{row.image_names?.length === 1 ? "" : "s"}</td><td>{formatDate(row.updated_at || row.created_at)}</td><td><button className="table-action" onClick={() => onOpen(row)}>Open <span>→</span></button></td></tr>;
  })}</tbody></table></div>;
}

function ReviewWorkspace({ inspection, previews, selectedImage, onSelectImage, openRules, onToggleRule, reviewer, reasons, setReason, onDecision, onExport, onPrint }: {
  inspection: InspectionRecord;
  previews: string[];
  selectedImage: number;
  onSelectImage: (index: number) => void;
  openRules: Set<string>;
  onToggleRule: (id: string) => void;
  reviewer: boolean;
  reasons: Record<string, string>;
  setReason: (id: string, reason: string) => void;
  onDecision: (rule: RuleResult, decision: Decision) => void;
  onExport: () => void;
  onPrint: () => void;
}) {
  const extraction = inspection.extraction;
  const assessment = inspection.assessment;
  const product = extraction?.product;
  const imageSources = inspection.image_urls?.length ? inspection.image_urls : previews;
  const rawText = extraction?.raw_text_by_image?.join("\n\n") || "No raw extraction text returned.";
  const rules = assessment?.results || [];
  const decided = Object.keys(inspection.review_decisions || {}).length;

  return <div className="review-page page-content">
    <WorkflowRail current={5} />
    <header className="review-title"><div><p className="eyebrow">{inspection.id} · {inspection.provider || "EVIDENCE SCREENING"}</p><h2>{product?.name || inspection.context.commodity_type || "Unknown packaged commodity"}</h2><p>{product?.brand || "Brand not extracted"} · {formatDate(inspection.created_at)} · Ruleset {assessment?.ruleset_version || RULESET_VERSION}</p></div><div className="review-actions"><button className="button button-secondary" onClick={onExport}>Export JSON</button><button className="button button-dark" onClick={onPrint}>Print / PDF</button></div></header>
    <section className="summary-band"><div><span>Overall screening</span><Badge status={assessment?.overall_status}>{assessment?.overall_label || statusLabel(assessment?.overall_status)}</Badge><small>Human review required before legal finalization</small></div><div><span>Passed</span><strong>{assessment?.counts?.PASS || 0}</strong></div><div><span>Needs review</span><strong>{assessment?.counts?.REVIEW || 0}</strong></div><div><span>Potential issues</span><strong>{assessment?.counts?.FAIL || 0}</strong></div><div><span>Reviewer decisions</span><strong>{decided} / {rules.length}</strong></div></section>

    <div className="review-grid">
      <div className="review-column">
        <section className="content-card evidence-card"><header className="card-heading"><div><p className="eyebrow">PACKAGE EVIDENCE</p><h3>Source images</h3></div><Badge status={inspection.quality.status === "GOOD" ? "PASS" : inspection.quality.status === "POOR" ? "FAIL" : "REVIEW"}>{inspection.quality.status}</Badge></header>
          {imageSources.length ? <><div className="evidence-stage"><img src={imageSources[Math.min(selectedImage, imageSources.length - 1)]} alt={`Primary package evidence ${selectedImage + 1}`} /></div><div className="thumb-row">{imageSources.map((source, index) => <button className={selectedImage === index ? "is-active" : ""} key={`${source}-${index}`} onClick={() => onSelectImage(index)}><img src={source} alt={`Show package evidence ${index + 1}`} /><span>{index + 1}</span></button>)}</div></> : <EmptyState title="Image preview not persisted" body="Evidence names and extracted excerpts remain in the record. Reattach originals for visual re-review." />}
        </section>
        <section className="content-card"><p className="eyebrow">APPLICABILITY ROUTE</p><h3>Why these checks?</h3><dl className="route-list"><div><dt>Market route</dt><dd>{inspection.context.package_context}</dd></div><div><dt>Commodity</dt><dd>{inspection.context.commodity_type}</dd></div><div><dt>Date required</dt><dd>{inspection.context.date_required}</dd></div><div><dt>Medical device</dt><dd>{inspection.context.medical_device}</dd></div></dl><p className="route-note">Checks were selected from context and visible evidence—not from an inspector-selected legal ruleset.</p></section>
      </div>

      <div className="review-column">
        <section className="content-card"><header className="card-heading"><div><p className="eyebrow">INFORMATION FOUND</p><h3>Extracted declarations</h3></div><span className="count-badge">AI + EVIDENCE</span></header>
          <div className="fact-list">{FIELD_DEFINITIONS.map(([label, key]) => {
            const value = extraction?.[key];
            const candidates = Array.isArray(value) ? value as Candidate[] : [];
            return <div className="fact-row" key={String(key)}><header><strong>{label}</strong>{candidates.length ? <span className={candidates[0].confidence >= 0.85 ? "high-confidence" : "low-confidence"}>{Math.round(candidates[0].confidence * 100)}% extraction confidence</span> : <span className="low-confidence">Not found</span>}</header>{candidates.length ? candidates.map((candidate, index) => <p key={`${candidate.value}-${index}`}>{candidate.qualifier ? `${candidate.qualifier}: ` : ""}{candidate.value}<small>“{candidate.evidence_excerpt || candidate.value}” · Image {candidate.image_index + 1}</small></p>) : <p>—<small>Absence is not treated as a confirmed issue unless panel coverage is established.</small></p>}</div>;
          })}</div>
          <details><summary>Show raw extracted text</summary><pre className="raw-text">{rawText}</pre></details>
        </section>
        <section className="content-card"><p className="eyebrow">COVERAGE & ASSURANCE</p><h3>{extraction?.coverage.mandatory_panel_visible === "YES" ? "Declaration panel visible" : extraction?.coverage.mandatory_panel_visible === "NO" ? "Declaration panel not shown" : "Panel coverage uncertain"}</h3><p className="coverage-note">{extraction?.coverage.notes || "No coverage note returned."}</p><div className="confidence-gate"><span>Validated extraction</span><strong>≥ 85% confidence</strong><small>plus field match and field-specific validation. Otherwise: Needs review.</small></div></section>
      </div>

      <div className="review-column checks-column">
        <section className="content-card"><header className="card-heading"><div><p className="eyebrow">APPLICABLE CHECKS</p><h3>Why this result?</h3><p>Open a check to inspect the full evidence chain.</p></div><span className="count-badge">{rules.length} RULES</span></header>
          <div className="result-list">{rules.map((rule, index) => {
            const isOpen = openRules.has(rule.rule_id);
            const existingDecision = reviewDecisionValue(inspection.review_decisions?.[rule.rule_id]);
            return <article className={`rule-result ${isOpen ? "is-open" : ""}`} key={rule.rule_id}>
              <button className="rule-summary" onClick={() => onToggleRule(rule.rule_id)} aria-expanded={isOpen}><span className="rule-number">0{index + 1}</span><span><strong>{rule.title}</strong><small>{rule.rule_id} · {rule.source}</small></span><Badge status={rule.status}>{rule.ui_label || statusLabel(rule.status)}</Badge><i>⌄</i></button>
              {isOpen && <div className="rule-detail"><p>{rule.explanation}</p><div className="rule-meta"><span>{rule.verification_mode}</span><span>{assessment?.ruleset_version || RULESET_VERSION}</span><span>Legal engine: {rule.legal_output}</span></div>
                <div className="evidence-list">{rule.evidence?.length ? rule.evidence.map((evidence) => <div className="evidence-box" key={evidence.id}><small>Image {(evidence.image_index ?? 0) + 1} · {evidence.confidence == null ? "visual predicate" : `${Math.round(evidence.confidence * 100)}% extraction confidence`} · {evidence.method}</small><p>“{evidence.excerpt || evidence.value || "No exact excerpt"}”</p></div>) : <div className="evidence-box"><p>No supporting excerpt was extracted.</p></div>}</div>
                {rule.next_action && <div className="next-action"><strong>Next action</strong><p>{rule.next_action}</p></div>}
                {reviewer ? <div className="review-controls"><label>Audit reason<textarea value={reasons[rule.rule_id] || ""} onChange={(event) => setReason(rule.rule_id, event.target.value)} placeholder="State what the evidence supports and why…" /></label><div>{REVIEW_DECISIONS.map(([decision, label]) => <button className={existingDecision === decision ? "is-selected" : ""} key={decision} onClick={() => onDecision(rule, decision)}>{label}</button>)}</div>{existingDecision && <small>Recorded disposition: {existingDecision.replaceAll("_", " ")}</small>}</div> : <div className="readonly-note">Read-only evidence view. Legal Reviewer or Administrator authority is required to record a disposition.</div>}
              </div>}
            </article>;
          })}</div>
        </section>
        <section className="content-card guardrail-card"><p className="eyebrow">GUARDRAILS</p><ul>{(assessment?.guardrails || ["Automated screening is not a final legal determination."]).map((guardrail) => <li key={guardrail}><span>✓</span>{guardrail}</li>)}</ul></section>
      </div>
    </div>
  </div>;
}
