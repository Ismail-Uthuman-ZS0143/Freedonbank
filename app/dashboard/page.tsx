"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import WorkspaceNav from "../components/WorkspaceNav";

interface Me { id: number; email: string; fullName: string; isStaff: boolean; }
interface FieldResult { ok: boolean; message: string; }
interface FieldResults {
  borrowerName: FieldResult; phone: FieldResult; email: FieldResult; companyName: FieldResult;
}
interface RequestRow {
  id: number; borrowerName: string; phone: string; email: string; companyName: string;
  status: "draft" | "sent" | "uploads_complete" | "expired" | "fraud_stopped";
  referenceNumber: string | null; hasFlaggedItems: boolean;
  linkToken: string | null; linkExpiresAt: string | null; createdAt: string; sentAt: string | null;
}
interface Metrics {
  activeRequests: number; docsInParkingBay: number | null;
  awaitingCustomer: number; sessionsEndedFraud: number | null;
  loansByStage: { documents: number; extraction: number };
  twinsCreatedThisMonth: number; pctValuesAutoVerified: number | null; avgRequestToExtractionDays: number | null;
}
interface AttentionItem { type: "fraud" | "flagged" | "hitl"; requestId: number | null; title: string; detail: string; }
interface SearchResult { kind: "request" | "checklistItem" | "extractedValue"; requestId: number; title: string; detail: string; }

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  draft: { label: "Draft", className: "badge info" },
  sent: { label: "Sent · link active", className: "badge info" },
  uploads_complete: { label: "Uploads complete", className: "badge ok" },
  expired: { label: "Link expired · no upload", className: "badge warn" },
  fraud_stopped: { label: "Session ended — fraud guard", className: "badge bad" },
};

interface EmailPreview {
  toEmail: string; fromEmail: string; subject: string; bodyText: string; sentAt: string;
  deliveryAttempted: boolean; delivered: boolean;
}

function EmailPreviewModal({ requestId, onClose }: { requestId: number; onClose: () => void }) {
  const [email, setEmail] = useState<EmailPreview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/requests/${requestId}/email`)
      .then(async r => {
        if (!r.ok) {
          const d = await r.json();
          throw new Error(d.error || 'Could not load this email.');
        }
        return r.json();
      })
      .then(setEmail)
      .catch(e => setError(e.message));
  }, [requestId]);

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 50, background: "rgba(16,28,66,.5)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}
      onClick={onClose}>
      <div style={{ background: "white", borderRadius: 16, width: "100%", maxWidth: 640, maxHeight: "85vh", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 24px 60px -30px rgba(16,28,66,.35)" }}
        onClick={e => e.stopPropagation()}>
        <div style={{ padding: "16px 22px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "center", background: "var(--ice)" }}>
          <b style={{ fontFamily: "var(--display)", color: "var(--navy)" }}>Secure request email</b>
          <button className="btn ghost" style={{ marginLeft: "auto", padding: "5px 10px" }} onClick={onClose}>Close</button>
        </div>
        <div style={{ padding: 22, overflowY: "auto" }}>
          {error && <p className="formnote">{error}</p>}
          {!error && !email && <p style={{ color: "var(--muted)" }}>Loading…</p>}
          {email && (
            <>
              {email.deliveryAttempted && (
                <span className={email.delivered ? "badge ok" : "badge bad"} style={{ marginBottom: 12, display: "inline-block" }}>
                  {email.delivered ? "✓ Delivered" : "✕ Delivery failed"}
                </span>
              )}
              <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 4 }}><b>From:</b> {email.fromEmail}</p>
              <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 4 }}><b>To:</b> {email.toEmail}</p>
              <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 12 }}><b>Subject:</b> {email.subject}</p>
              <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--body)", fontSize: 13.5, lineHeight: 1.6, background: "var(--ice)", borderRadius: 10, padding: 16, margin: 0 }}>
                {email.bodyText}
              </pre>
              <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 12 }}>
                {email.delivered
                  ? `Delivered ${new Date(email.sentAt).toLocaleString()} via direct-to-MX SMTP (no relay/provider).`
                  : `Logged ${new Date(email.sentAt).toLocaleString()} — real delivery was attempted and failed (or is disabled/blocked by the domain allowlist); see the backend log for the reason.`}
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

interface UploadedFileRow {
  id: number; fileName: string; fileType: string; fileSize: number; checklistItemId: number | null; uploadedAt: string;
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FilesModal({ requestId, onClose }: { requestId: number; onClose: () => void }) {
  const [files, setFiles] = useState<UploadedFileRow[] | null>(null);

  useEffect(() => {
    fetch(`/api/requests/${requestId}/uploads`).then(r => r.json()).then(setFiles);
  }, [requestId]);

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 50, background: "rgba(16,28,66,.5)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}
      onClick={onClose}>
      <div style={{ background: "white", borderRadius: 16, width: "100%", maxWidth: 520, maxHeight: "80vh", display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 24px 60px -30px rgba(16,28,66,.35)" }}
        onClick={e => e.stopPropagation()}>
        <div style={{ padding: "16px 22px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "center", background: "var(--ice)" }}>
          <b style={{ fontFamily: "var(--display)", color: "var(--navy)" }}>Parking bay — uploaded documents</b>
          <button className="btn ghost" style={{ marginLeft: "auto", padding: "5px 10px" }} onClick={onClose}>Close</button>
        </div>
        <div style={{ padding: 16, overflowY: "auto" }}>
          {!files && <p style={{ color: "var(--muted)" }}>Loading…</p>}
          {files?.length === 0 && <p style={{ color: "var(--muted)", fontSize: 13.5 }}>No documents uploaded yet.</p>}
          {files?.map(f => (
            <div key={f.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 6px", borderTop: "1px solid var(--line-soft)", fontSize: 13.5 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 500 }}>{f.fileName}</div>
                <div style={{ fontSize: 11.5, color: "var(--muted)" }}>{formatBytes(f.fileSize)} · {new Date(f.uploadedAt).toLocaleString()}</div>
              </div>
              <a className="btn ghost" style={{ padding: "5px 10px", fontSize: 12 }}
                href={`/api/requests/${requestId}/uploads/${f.id}/serve`} target="_blank" rel="noopener noreferrer">View</a>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function initials(fullName: string) {
  const parts = fullName.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return fullName.slice(0, 2).toUpperCase();
}

export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [checking, setChecking] = useState(true);

  const [borrowerName, setBorrowerName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [fieldResults, setFieldResults] = useState<FieldResults | null>(null);
  const [sending, setSending] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [viewingEmailFor, setViewingEmailFor] = useState<number | null>(null);
  const [viewingFilesFor, setViewingFilesFor] = useState<number | null>(null);
  const [attention, setAttention] = useState<AttentionItem[] | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    fetch("/api/auth/me")
      .then(r => r.json())
      .then(d => {
        if (!d.user) {
          router.replace("/");
          return;
        }
        setMe(d.user);
      })
      .finally(() => setChecking(false));
  }, [router]);

  const loadRequests = useCallback(async () => {
    const res = await fetch("/api/requests");
    if (!res.ok) return;
    const data = await res.json();
    setRequests(data.requests);
    setMetrics(data.metrics);
  }, []);

  useEffect(() => { if (me) loadRequests(); }, [me, loadRequests]);

  useEffect(() => {
    if (!me) return;
    fetch("/api/requests/needs-attention").then(r => r.json()).then(d => setAttention(d.items));
  }, [me, requests]);

  useEffect(() => {
    if (!searchQuery.trim()) { setSearchResults(null); return; }
    setSearching(true);
    const handle = setTimeout(() => {
      fetch(`/api/requests/search?q=${encodeURIComponent(searchQuery)}`)
        .then(r => r.json())
        .then(d => setSearchResults(d.results))
        .finally(() => setSearching(false));
    }, 300);
    return () => clearTimeout(handle);
  }, [searchQuery]);

  const validateFields = async () => {
    const res = await fetch("/api/requests/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ borrowerName, phone, email, companyName }),
    });
    const data: FieldResults = await res.json();
    setFieldResults(data);
    return data;
  };

  const allValid = (results: FieldResults) =>
    results.borrowerName.ok && results.phone.ok && results.email.ok && results.companyName.ok;

  const handleSend = async () => {
    setFormError(null);
    const results = await validateFields();
    if (!allValid(results)) return;

    setSending(true);
    try {
      const res = await fetch("/api/requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ borrowerName, phone, email, companyName, action: "send" }),
      });
      const data = await res.json();
      if (!res.ok) {
        setFormError(data.error || "Could not send the request.");
        return;
      }
      setBorrowerName(""); setPhone(""); setEmail(""); setCompanyName(""); setFieldResults(null);
      await loadRequests();
    } finally {
      setSending(false);
    }
  };

  const handleSaveDraft = async () => {
    setFormError(null);
    if (!borrowerName.trim()) {
      setFormError("Borrower name is required, even for a draft.");
      return;
    }
    setSavingDraft(true);
    try {
      const res = await fetch("/api/requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ borrowerName, phone, email, companyName, action: "draft" }),
      });
      const data = await res.json();
      if (!res.ok) {
        setFormError(data.error || "Could not save the draft.");
        return;
      }
      setBorrowerName(""); setPhone(""); setEmail(""); setCompanyName(""); setFieldResults(null);
      await loadRequests();
    } finally {
      setSavingDraft(false);
    }
  };

  const handleResend = async (id: number) => {
    const res = await fetch(`/api/requests/${id}/resend`, { method: "POST" });
    if (res.ok) await loadRequests();
  };

  const [copiedId, setCopiedId] = useState<number | null>(null);
  const handleCopyLink = async (r: RequestRow) => {
    if (!r.linkToken) return;
    await navigator.clipboard.writeText(`${window.location.origin}/upload/${r.linkToken}`);
    setCopiedId(r.id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  const handleSignOut = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    router.replace("/");
  };

  if (checking || !me) return null;

  const fieldClass = (field: keyof FieldResults) => {
    if (!fieldResults) return "field";
    return `field ${fieldResults[field].ok ? "ok" : "bad"}`;
  };

  return (
    <div className="dash-page">
      <div className="topbar2">
        <span className="name">Credit File Server 2.0</span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
          <span>{me.fullName}</span>
          <button className="btn ghost" onClick={() => router.push("/settings/checklist")}>Checklist settings</button>
          <button className="btn ghost" onClick={handleSignOut}>Sign out</button>
        </div>
      </div>

      <div className="dash">
        <div className="dhead">
          <h3>Credit audit</h3>
          <div className="who">Commercial banking <span className="avatar">{initials(me.fullName)}</span></div>
        </div>

        <WorkspaceNav activeCount={metrics?.activeRequests} />

        <div style={{ position: "relative", marginBottom: 18 }}>
          <input type="search" value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search the document estate — borrower, company, checklist item, extracted value…"
            style={{ width: "100%", padding: "11px 16px", borderRadius: 10, border: "1.5px solid var(--line)", fontSize: 13.5 }} />
          {searchQuery.trim() && (
            <div style={{
              position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 10,
              background: "white", border: "1px solid var(--line)", borderRadius: 10,
              boxShadow: "0 12px 30px -12px rgba(16,28,66,.25)", maxHeight: 320, overflowY: "auto",
            }}>
              {searching && <p style={{ padding: 14, fontSize: 12.5, color: "var(--muted)" }}>Searching…</p>}
              {!searching && searchResults?.length === 0 && (
                <p style={{ padding: 14, fontSize: 12.5, color: "var(--muted)" }}>No matches for &quot;{searchQuery}&quot;.</p>
              )}
              {!searching && searchResults?.map((r, i) => (
                <div key={i} onClick={() => { router.push(`/parking-bay/${r.requestId}`); setSearchQuery(""); }}
                  style={{ padding: "10px 14px", borderTop: i > 0 ? "1px solid var(--line-soft)" : "none", cursor: "pointer", fontSize: 13 }}>
                  <span className="badge info" style={{ marginRight: 8, fontSize: 10 }}>
                    {r.kind === "request" ? "Request" : r.kind === "checklistItem" ? "Checklist item" : "Extracted value"}
                  </span>
                  <b>{r.title}</b>
                  {r.detail && <span style={{ color: "var(--muted)" }}> · {r.detail}</span>}
                </div>
              ))}
            </div>
          )}
        </div>

        {metrics && (
          <div className="statstrip">
            <span><b>{metrics.twinsCreatedThisMonth}</b> twins created this month</span>
            <span><b>{metrics.pctValuesAutoVerified !== null ? `${metrics.pctValuesAutoVerified}%` : "—"}</b> values auto-verified · no touch</span>
            <span><b>{metrics.avgRequestToExtractionDays !== null ? `${metrics.avgRequestToExtractionDays} days` : "—"}</b> avg request → extraction</span>
          </div>
        )}

        <div className="metrics">
          <div className="metric">
            <div className="k">Active requests</div>
            <div className="v">{metrics?.activeRequests ?? "—"}</div>
          </div>
          <div className="metric">
            <div className="k">Docs in parking bay</div>
            <div className="v">{metrics?.docsInParkingBay ?? "—"}</div>
          </div>
          <div className="metric">
            <div className="k">Awaiting customer</div>
            <div className="v">{metrics?.awaitingCustomer ?? "—"}</div>
          </div>
          <div className="metric hot">
            <div className="k">Sessions ended — fraud</div>
            <div className="v bad">{metrics?.sessionsEndedFraud ?? "—"}</div>
          </div>
        </div>

        {metrics && (metrics.loansByStage.documents + metrics.loansByStage.extraction > 0) && (
          <div className="panel">
            <div className="phead">
              <h4>Loans in flight — by stage</h4>
              <span className="note">Documents · Extraction only — later stages aren&apos;t built yet</span>
            </div>
            {(() => {
              const { documents, extraction } = metrics.loansByStage;
              const total = documents + extraction;
              return (
                <>
                  <div style={{ display: "flex", height: 10, borderRadius: 999, overflow: "hidden", marginBottom: 10 }}>
                    <div style={{ width: `${(documents / total) * 100}%`, background: "var(--navy)" }} title={`Documents · ${documents}`} />
                    <div style={{ width: `${(extraction / total) * 100}%`, background: "var(--gold)" }} title={`Extraction · ${extraction}`} />
                  </div>
                  <div style={{ display: "flex", gap: 16, fontSize: 12.5, color: "var(--muted)" }}>
                    <span><span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "var(--navy)", marginRight: 6 }} />Documents · {documents}</span>
                    <span><span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "var(--gold)", marginRight: 6 }} />Extraction · {extraction}</span>
                  </div>
                </>
              );
            })()}
          </div>
        )}

        {attention && attention.length > 0 && (
          <div className="panel">
            <div className="phead"><h4>Needs attention</h4><span className="note">{attention.length} item{attention.length === 1 ? "" : "s"}</span></div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {attention.map((a, i) => (
                <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 10, fontSize: 13 }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: "50%", marginTop: 5, flexShrink: 0,
                    background: a.type === "fraud" ? "var(--bad)" : a.type === "flagged" ? "var(--gold)" : "var(--navy)",
                  }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <b>{a.title}</b>
                    {a.detail && <div style={{ fontSize: 12, color: "var(--muted)" }}>{a.detail}</div>}
                  </div>
                  {a.requestId !== null && (
                    <button className="btn ghost" style={{ padding: "5px 10px", fontSize: 12 }} onClick={() => router.push(`/parking-bay/${a.requestId}`)}>
                      Open
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="panel">
          <div className="phead">
            <h4>New document request · applicant details</h4>
            <span className="note">fields validated before send</span>
          </div>
          <div className="fgrid">
            <div className={fieldClass("borrowerName")}>
              <label htmlFor="f-name">Borrower name</label>
              <input id="f-name" type="text" value={borrowerName}
                onChange={e => setBorrowerName(e.target.value)} onBlur={validateFields} />
              {fieldResults && <div className={`hint ${fieldResults.borrowerName.ok ? "ok" : "bad"}`}>{fieldResults.borrowerName.message}</div>}
            </div>
            <div className={fieldClass("phone")}>
              <label htmlFor="f-phone">Phone</label>
              <input id="f-phone" type="tel" value={phone}
                onChange={e => setPhone(e.target.value)} onBlur={validateFields} />
              {fieldResults && <div className={`hint ${fieldResults.phone.ok ? "ok" : "bad"}`}>{fieldResults.phone.message}</div>}
            </div>
            <div className={fieldClass("email")}>
              <label htmlFor="f-email">Email</label>
              <input id="f-email" type="email" value={email}
                onChange={e => setEmail(e.target.value)} onBlur={validateFields} />
              {fieldResults && <div className={`hint ${fieldResults.email.ok ? "ok" : "bad"}`}>{fieldResults.email.message}</div>}
            </div>
            <div className={fieldClass("companyName")}>
              <label htmlFor="f-co">Company name</label>
              <input id="f-co" type="text" value={companyName}
                onChange={e => setCompanyName(e.target.value)} onBlur={validateFields} />
              {fieldResults && <div className={`hint ${fieldResults.companyName.ok ? "ok" : "bad"}`}>{fieldResults.companyName.message}</div>}
            </div>
          </div>
          {formError && <p className="formnote" style={{ marginTop: 16 }}>{formError}</p>}
          <div className="factions">
            <button className="btn primary" onClick={handleSend} disabled={sending}>
              {sending ? "Sending…" : "Send secure request"}
            </button>
            <button className="btn ghost" onClick={handleSaveDraft} disabled={savingDraft}>
              {savingDraft ? "Saving…" : "Save draft"}
            </button>
            <span className="note">
              🔒 Emails the customer an encrypted upload link — document list comes from your{" "}
              <a href="/settings/checklist" style={{ color: "var(--navy)", fontWeight: 600 }}>configured checklist</a>
            </span>
          </div>
        </div>

        {viewingEmailFor !== null && (
          <EmailPreviewModal requestId={viewingEmailFor} onClose={() => setViewingEmailFor(null)} />
        )}
        {viewingFilesFor !== null && (
          <FilesModal requestId={viewingFilesFor} onClose={() => setViewingFilesFor(null)} />
        )}

        <div className="panel" style={{ marginBottom: 6 }}>
          <div className="phead"><h4>Recent requests</h4><span className="note">resend available until uploads complete</span></div>
          {requests.length === 0 && <p style={{ color: "var(--muted)", fontSize: 13.5 }}>No requests yet.</p>}
          {requests.map(r => {
            const badge = STATUS_BADGE[r.status];
            const canUpload = r.status === "sent" || r.status === "uploads_complete";
            return (
              <div className="rrow" key={r.id}>
                <div className="who2">
                  <b>{r.borrowerName}</b> {r.companyName && <>· <span className="co">{r.companyName}</span></>}
                  {r.referenceNumber && <span className="co"> · Reference {r.referenceNumber}</span>}
                </div>
                <span className={badge.className}>{badge.label}</span>
                {r.hasFlaggedItems && <span className="badge warn">⚑ Flagged — needs re-upload</span>}
                {r.status !== "draft" && (
                  <button className="btn ghost" onClick={() => setViewingEmailFor(r.id)}>View email</button>
                )}
                {canUpload && (
                  <button className="btn ghost" onClick={() => setViewingFilesFor(r.id)}>View docs</button>
                )}
                {canUpload && (
                  <button className="btn ghost" onClick={() => router.push(`/parking-bay/${r.id}`)}>Review</button>
                )}
                {r.status === "sent" && r.linkToken && (
                  <button className="btn ghost" onClick={() => handleCopyLink(r)}>
                    {copiedId === r.id ? "Copied!" : "Copy link"}
                  </button>
                )}
                {r.status === "sent" || r.status === "expired" || r.status === "fraud_stopped" ? (
                  <button className="btn ghost" onClick={() => handleResend(r.id)}>Resend</button>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
