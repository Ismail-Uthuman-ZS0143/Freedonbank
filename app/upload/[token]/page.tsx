"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams } from "next/navigation";

interface ChecklistItemRow { id: number; name: string; category: string; status: "pending" | "uploaded"; fileName: string | null; }
interface UploadInfo {
  borrowerName: string; companyName: string; email: string; status: string; error: string | null;
  referenceNumber: string | null; sessionSecondsRemaining: number | null; items: ChecklistItemRow[];
}

function formatClock(totalSeconds: number) {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function UploadPortalPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;

  const [info, setInfo] = useState<UploadInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [uploadingId, setUploadingId] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const activeItemId = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/upload/${token}`);
      const data = await res.json();
      if (!res.ok) {
        setInfo(data);
        setFatalError(data.error || "This upload link is invalid.");
      } else {
        setInfo(data);
        setFatalError(null);
        setSecondsLeft(data.sessionSecondsRemaining);
      }
    } catch {
      setFatalError("Could not reach the upload service.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  // Client-side countdown, ticking down between server syncs.
  useEffect(() => {
    if (secondsLeft === null || secondsLeft <= 0) return;
    const t = setInterval(() => setSecondsLeft(s => (s !== null && s > 0 ? s - 1 : s)), 1000);
    return () => clearInterval(t);
  }, [secondsLeft]);

  const triggerUpload = (itemId: number) => {
    activeItemId.current = itemId;
    fileInputRef.current?.click();
  };

  const handleFile = async (file: File) => {
    const itemId = activeItemId.current;
    if (!itemId) return;
    setUploadingId(itemId);
    setUploadError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("checklistItemId", String(itemId));
      const res = await fetch(`/api/upload/${token}/documents`, { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) {
        setUploadError(data.error || "Upload failed.");
        if (res.status === 410) await load(); // session expired / fraud-stopped -- refresh to terminal state
        return;
      }
      await load();
    } catch {
      setUploadError("Upload failed — check your connection and try again.");
    } finally {
      setUploadingId(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const sessionTimedOut = secondsLeft === 0;

  return (
    <div className="login-page">
      <div style={{ background: "white", borderRadius: 16, width: "100%", maxWidth: 560, boxShadow: "0 24px 60px -30px rgba(16,28,66,.3)", overflow: "hidden" }}>
        <div style={{ padding: "20px 28px", borderBottom: "1px solid var(--line)", background: "var(--navy)", color: "white" }}>
          <b style={{ fontFamily: "var(--display)" }}>Freedom Bank of Virginia</b>
          <p style={{ fontSize: 12.5, color: "var(--navy-100)", marginTop: 2 }}>Secure document upload</p>
        </div>

        <div style={{ padding: 28 }}>
          {loading ? (
            <p style={{ color: "var(--muted)" }}>Loading…</p>
          ) : fatalError ? (
            <div style={{ textAlign: "center", padding: "20px 0" }}>
              <div style={{ fontSize: 32, marginBottom: 10 }}>
                {info?.status === "uploads_complete" ? "✓" : info?.status === "fraud_stopped" ? "🛡️" : "✕"}
              </div>
              <h3 style={{ marginBottom: 8 }}>
                {info?.status === "fraud_stopped" ? "Session ended — unusual activity detected" : "This link isn't available"}
              </h3>
              <p style={{ color: "var(--muted)", fontSize: 14 }}>{fatalError}</p>
            </div>
          ) : info?.status === "uploads_complete" ? (
            <div style={{ textAlign: "center", padding: "20px 0" }}>
              <div style={{ fontSize: 32, marginBottom: 10, color: "var(--ok)" }}>✓</div>
              <h3 style={{ marginBottom: 8 }}>Thanks for uploading</h3>
              <p style={{ color: "var(--muted)", fontSize: 14 }}>
                All requested documents are in the secure parking bay. The FBOV team will review them and reach out with next steps.
              </p>
              {info.referenceNumber && (
                <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 10 }}>Reference {info.referenceNumber}</p>
              )}
              {info.email && (
                <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 4 }}>
                  Confirmation email sent to {info.email} from the platform.
                </p>
              )}
            </div>
          ) : (
            <>
              <h3 style={{ marginBottom: 2 }}>Document upload — {info?.companyName || info?.borrowerName}</h3>
              <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 16 }}>Commercial loan application</p>

              {secondsLeft !== null && (
                <div style={{
                  display: "inline-flex", alignItems: "center", gap: 8, fontSize: 12.5, fontWeight: 600,
                  padding: "6px 12px", borderRadius: 999, marginBottom: 16,
                  background: sessionTimedOut ? "var(--bad-bg)" : "var(--ice)",
                  color: sessionTimedOut ? "var(--bad)" : "var(--navy)",
                }}>
                  ⏱ {sessionTimedOut ? "Session expired" : `${formatClock(secondsLeft)} session remaining`}
                </div>
              )}

              <div style={{ background: "var(--ice)", borderRadius: 10, padding: "10px 14px", fontSize: 12.5, color: "var(--muted)", marginBottom: 16 }}>
                📦 <b>Temporary parking bay:</b> your files are held securely here until the FBOV team reviews them.
              </div>

              <input ref={fileInputRef} type="file" style={{ display: "none" }}
                onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />

              {uploadError && <p className="formnote" style={{ marginBottom: 12 }}>{uploadError}</p>}

              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {(() => {
                  let lastCategory: string | null = null;
                  return info?.items.map(item => {
                    const showGroup = item.category && item.category !== lastCategory;
                    lastCategory = item.category;
                    return (
                      <div key={item.id}>
                        {showGroup && (
                          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--muted)", margin: "10px 0 4px", textTransform: "uppercase", letterSpacing: 0.3 }}>
                            {item.category}
                          </div>
                        )}
                        <div style={{
                          display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", borderRadius: 10,
                          border: "1px solid var(--line)", background: item.status === "uploaded" ? "var(--ok-bg)" : "var(--paper)",
                        }}>
                          <span style={{ flexShrink: 0 }}>{item.status === "uploaded" ? "✓" : "○"}</span>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 13.5, fontWeight: 500 }}>{item.name}</div>
                            {item.fileName && <div style={{ fontSize: 11.5, color: "var(--muted)" }}>{item.fileName}</div>}
                          </div>
                          <button className="btn ghost" style={{ padding: "6px 12px", fontSize: 12 }}
                            disabled={sessionTimedOut || uploadingId === item.id}
                            onClick={() => triggerUpload(item.id)}>
                            {uploadingId === item.id ? "Uploading…" : item.status === "uploaded" ? "Replace" : "Choose file"}
                          </button>
                        </div>
                      </div>
                    );
                  });
                })()}
              </div>

              <div style={{ marginTop: 18, padding: "10px 14px", background: "var(--warn-bg)", borderRadius: 10, fontSize: 12, color: "var(--warn)" }}>
                🛡️ <b>Session guard is active.</b> Unusual activity ends this session immediately; anything already uploaded is kept.
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
