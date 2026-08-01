"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import WorkspaceNav from "../../components/WorkspaceNav";

interface Me { id: number; email: string; fullName: string; isStaff: boolean; }

interface ReviewFile {
  id: number; fileName: string; fileType: string; fileSize: number; uploadedAt: string;
  reviewStatus: "pending" | "approved" | "flagged"; reviewComment: string; reviewedAt: string | null;
}
interface ReviewItem {
  id: number; name: string; status: "pending" | "uploaded"; file: ReviewFile | null;
}
interface ParkingBay {
  id: number; borrowerName: string; companyName: string; referenceNumber: string | null;
  extractionQueuedAt: string | null; items: ReviewItem[];
  reviewComplete: boolean; approvedCount: number; flaggedCount: number;
}

const REVIEW_BADGE: Record<string, { label: string; className: string }> = {
  pending: { label: "Pending review", className: "badge info" },
  approved: { label: "Ready for extraction", className: "badge ok" },
  flagged: { label: "Flagged — re-upload", className: "badge warn" },
};

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// The macro pipeline beyond "Documents" (Credit review onward) isn't built
// yet -- this is a static "you are here" indicator over real state we do
// track (whether extraction has been queued), not a fake live tracker for
// steps that don't exist.
const LOAN_STAGES = ["Request", "Documents", "Extraction", "Credit review", "Term sheet", "Decision", "Commitment", "Signed", "Processing"];

function LoanStatusStepper({ extractionQueued }: { extractionQueued: boolean }) {
  const currentIndex = extractionQueued ? 2 : 1;
  return (
    <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6, fontSize: 11.5, marginBottom: 16 }}>
      {LOAN_STAGES.map((stage, i) => (
        <span key={stage} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{
            padding: "3px 9px", borderRadius: 999, fontWeight: 600,
            background: i < currentIndex ? "var(--ok-bg)" : i === currentIndex ? "var(--navy-100)" : "var(--ice)",
            color: i < currentIndex ? "var(--ok)" : i === currentIndex ? "var(--navy)" : "var(--muted)",
          }}>
            {i < currentIndex ? "✓ " : i === currentIndex ? "● " : ""}{stage}
          </span>
          {i < LOAN_STAGES.length - 1 && <span style={{ color: "var(--line)" }}>→</span>}
        </span>
      ))}
    </div>
  );
}

export default function ParkingBayPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const requestId = params.id;

  const [me, setMe] = useState<Me | null>(null);
  const [checking, setChecking] = useState(true);
  const [bay, setBay] = useState<ParkingBay | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [flagsJustSent, setFlagsJustSent] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/auth/me")
      .then(r => r.json())
      .then(d => {
        if (!d.user) { router.replace("/"); return; }
        setMe(d.user);
      })
      .finally(() => setChecking(false));
  }, [router]);

  const load = useCallback(async () => {
    const res = await fetch(`/api/requests/${requestId}/parking-bay`);
    if (!res.ok) { setNotFound(true); return; }
    const data: ParkingBay = await res.json();
    setBay(data);
    setSelectedId(prev => (prev !== null ? prev : (data.items.find(i => i.file)?.id ?? data.items[0]?.id ?? null)));
  }, [requestId]);

  useEffect(() => { if (me) load(); }, [me, load]);

  const selected = bay?.items.find(i => i.id === selectedId) ?? null;

  useEffect(() => {
    setComment(selected?.file?.reviewComment ?? "");
    setActionError(null);
  }, [selectedId]);

  const submitReview = async (decision: "approve" | "flag") => {
    if (!selected) return;
    setActionError(null);
    setBusy(true);
    try {
      const res = await fetch(`/api/requests/${requestId}/parking-bay/${selected.id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, comment }),
      });
      const data = await res.json();
      if (!res.ok) { setActionError(data.error || "Could not save this decision."); return; }
      await load();
    } finally {
      setBusy(false);
    }
  };

  const sendFlagsEmail = async () => {
    setActionError(null);
    setBusy(true);
    try {
      const res = await fetch(`/api/requests/${requestId}/parking-bay/send-flags-email`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) { setActionError(data.error || "Could not send the email."); return; }
      setFlagsJustSent(data.flaggedCount);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const kickStartExtraction = async () => {
    setActionError(null);
    setBusy(true);
    try {
      const res = await fetch(`/api/requests/${requestId}/parking-bay/kick-start-extraction`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) { setActionError(data.error || "Could not start extraction."); return; }
      await load();
    } finally {
      setBusy(false);
    }
  };

  if (checking || !me) return null;

  return (
    <div className="dash-page">
      <div className="topbar2">
        <span className="name">Credit File Server 2.0</span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
          <button className="btn ghost" onClick={() => router.push("/dashboard")}>Back to dashboard</button>
        </div>
      </div>

      <div className="dash">
        {notFound && <p className="formnote">This request could not be found.</p>}
        {!notFound && !bay && <p style={{ color: "var(--muted)" }}>Loading…</p>}

        {bay && (
          <>
            <div className="dhead">
              <h3>Parking bay review — {bay.companyName || bay.borrowerName}</h3>
              <div className="who">
                {bay.referenceNumber && <span>Reference {bay.referenceNumber}</span>}
              </div>
            </div>

            <WorkspaceNav />

            <LoanStatusStepper extractionQueued={!!bay.extractionQueuedAt} />

            {actionError && <p className="formnote" style={{ marginBottom: 16 }}>{actionError}</p>}

            <div className="panel" style={{ display: "flex", gap: 20, padding: 0, overflow: "hidden" }}>
              <aside style={{ width: 280, flexShrink: 0, borderRight: "1px solid var(--line)", background: "var(--ice)" }}>
                <div style={{ padding: "14px 16px", fontSize: 12, fontWeight: 600, color: "var(--muted)", borderBottom: "1px solid var(--line)" }}>
                  Parking bay · {bay.items.filter(i => i.file).length} files
                </div>
                {bay.items.map(item => {
                  const badge = item.file ? REVIEW_BADGE[item.file.reviewStatus] : { label: "Awaiting upload", className: "badge info" };
                  return (
                    <div key={item.id}
                      onClick={() => item.file && setSelectedId(item.id)}
                      style={{
                        display: "flex", alignItems: "center", gap: 10, padding: "12px 16px",
                        borderBottom: "1px solid var(--line-soft)", cursor: item.file ? "pointer" : "default",
                        background: item.id === selectedId ? "var(--navy-100)" : "transparent",
                        opacity: item.file ? 1 : 0.6,
                      }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 500 }}>{item.file?.fileName ?? item.name}</div>
                        <div style={{ fontSize: 11, color: "var(--muted)" }}>{item.name}</div>
                      </div>
                      <span className={badge.className} style={{ flexShrink: 0 }}>{badge.label}</span>
                    </div>
                  );
                })}
              </aside>

              <div style={{ flex: 1, minWidth: 0, padding: "18px 20px" }}>
                {!selected?.file && <p style={{ color: "var(--muted)", fontSize: 13.5 }}>Select a file to review.</p>}
                {selected?.file && (
                  <>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
                      <h4 style={{ fontFamily: "var(--display)", color: "var(--navy)", fontSize: 15 }}>{selected.file.fileName}</h4>
                      <span className={REVIEW_BADGE[selected.file.reviewStatus].className}>{REVIEW_BADGE[selected.file.reviewStatus].label}</span>
                      <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)" }}>{selected.name} · {formatBytes(selected.file.fileSize)}</span>
                    </div>

                    <div style={{ background: "var(--ice)", borderRadius: 10, marginBottom: 16, minHeight: 220, display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
                      {selected.file.fileType.startsWith("image/") ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={`/api/requests/${requestId}/uploads/${selected.file.id}/serve`} alt={selected.file.fileName}
                          style={{ maxWidth: "100%", maxHeight: 320, objectFit: "contain" }} />
                      ) : selected.file.fileType === "application/pdf" ? (
                        <iframe src={`/api/requests/${requestId}/uploads/${selected.file.id}/serve`} title={selected.file.fileName}
                          style={{ width: "100%", height: 380, border: "none" }} />
                      ) : (
                        <div style={{ textAlign: "center", padding: 24 }}>
                          <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 10 }}>No inline preview for this file type.</p>
                          <a className="btn ghost" href={`/api/requests/${requestId}/uploads/${selected.file.id}/serve`} target="_blank" rel="noopener noreferrer">
                            Open / download
                          </a>
                        </div>
                      )}
                    </div>

                    <div className="dcard" style={{ border: "1px solid var(--navy-100)", borderRadius: 10, padding: 16 }}>
                      <h5 style={{ fontSize: 13, marginBottom: 6 }}>Review comments</h5>
                      <p style={{ fontSize: 12, color: "var(--muted)", marginBottom: 8 }}>
                        Optional — required only to flag something for re-upload. Flagged comments are bundled into one secure email from the review summary below; nothing is sent from this screen.
                      </p>
                      <textarea value={comment} onChange={e => setComment(e.target.value)}
                        placeholder="e.g. Statement covers FY2023 only — we need FY2024 and FY2025."
                        style={{ width: "100%", minHeight: 70, borderRadius: 8, border: "1.5px solid var(--line)", padding: 10, fontSize: 13, fontFamily: "inherit", marginBottom: 10 }} />
                      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                        <button className="btn primary" disabled={busy} onClick={() => submitReview("approve")}>Submit for extraction</button>
                        <button className="btn ghost" disabled={busy} onClick={() => submitReview("flag")}>Flag — needs re-upload</button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="panel" style={{ marginTop: 20 }}>
              <div className="phead">
                <h4>Review summary</h4>
                <span className="note">
                  {bay.reviewComplete ? `Review complete · ${bay.items.length} of ${bay.items.length}` : `${bay.approvedCount + bay.flaggedCount} of ${bay.items.length} reviewed`}
                </span>
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "var(--muted)", fontSize: 11.5 }}>
                    <th style={{ padding: "6px 8px" }}>Document</th>
                    <th style={{ padding: "6px 8px" }}>Checklist item</th>
                    <th style={{ padding: "6px 8px" }}>Reviewer decision</th>
                    <th style={{ padding: "6px 8px" }}>Comment</th>
                  </tr>
                </thead>
                <tbody>
                  {bay.items.map(item => {
                    const badge = item.file ? REVIEW_BADGE[item.file.reviewStatus] : { label: "Not uploaded", className: "badge info" };
                    return (
                      <tr key={item.id} style={{ borderTop: "1px solid var(--line-soft)" }}>
                        <td style={{ padding: "8px" }}><b>{item.file?.fileName ?? "—"}</b></td>
                        <td style={{ padding: "8px" }}>{item.name}</td>
                        <td style={{ padding: "8px" }}><span className={badge.className}>{badge.label}</span></td>
                        <td style={{ padding: "8px", color: "var(--muted)", fontSize: 12.5 }}>{item.file?.reviewComment || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 18, paddingTop: 16, borderTop: "1px solid var(--line)", flexWrap: "wrap" }}>
                {bay.flaggedCount > 0 && (
                  <button className="btn navy" disabled={busy} onClick={sendFlagsEmail}>
                    Send secure email · {bay.flaggedCount} flagged comment{bay.flaggedCount === 1 ? "" : "s"}
                  </button>
                )}
                {bay.extractionQueuedAt ? (
                  <>
                    <span className="badge ok">Extraction queued · {new Date(bay.extractionQueuedAt).toLocaleString()}</span>
                    <button className="btn ghost" onClick={() => router.push(`/extraction/${bay.id}`)}>Watch extraction →</button>
                  </>
                ) : (
                  <button className="btn primary" disabled={busy || !bay.reviewComplete || bay.approvedCount === 0} onClick={kickStartExtraction}>
                    Kick-start extraction · {bay.approvedCount} document{bay.approvedCount === 1 ? "" : "s"}
                  </button>
                )}
                <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)" }}>🔒 One email per request · extraction runs in Step 7</span>
              </div>
              {flagsJustSent !== null && (
                <p style={{ fontSize: 12, color: "var(--ok)", marginTop: 10 }}>
                  Secure email logged for {flagsJustSent} flagged document{flagsJustSent === 1 ? "" : "s"} (no real mail provider configured yet — inspect it from the dashboard&apos;s &quot;View email&quot;).
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
