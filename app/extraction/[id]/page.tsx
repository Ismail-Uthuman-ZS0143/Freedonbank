"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import WorkspaceNav from "../../components/WorkspaceNav";

interface Me { id: number; email: string; fullName: string; isStaff: boolean; }

interface ExtractedValue {
  id: number; fieldName: string; value: string; source: string; confidence: number; needsReview: boolean;
}
interface DocumentTwin {
  id: number; uploadedFileId: number; fileName: string; currentStage: string;
  classificationLabel: string; progressPercent: number; overallPercent: number;
  stages: Record<string, string | null>; extractedValues: ExtractedValue[];
}
interface BusinessTwin {
  id: number; currentStage: string; progressPercent: number; stages: Record<string, string | null>;
}
interface LogEntry { type: string; detail: string; at: string; documentTwinId: number | null; }
interface Extraction {
  requestId: number; referenceNumber: string | null;
  documentTwins: DocumentTwin[]; businessTwin: BusinessTwin | null; log: LogEntry[];
}

const DOCUMENT_STAGE_ORDER = ["received", "classified", "extracted", "provenance", "confidence"];
const DOCUMENT_STAGE_LABELS: Record<string, string> = {
  received: "Received", classified: "Classified", extracted: "Extracted",
  provenance: "Provenance", confidence: "Confidence",
};
// Matches BusinessTwin.STAGE_ORDER (snake_case, same as `currentStage`) --
// note this differs from the `stages` response dict, whose keys are camelCase.
const BUSINESS_STAGE_ORDER = ["relationship", "entities", "covenant_ledger", "indicators", "allocation"];
const BUSINESS_STAGE_LABELS: Record<string, string> = {
  relationship: "Relationship", entities: "Entities", covenant_ledger: "Covenant ledger",
  indicators: "Indicators", allocation: "Allocation",
};

function StageTrack({ order, labels, currentStage }: {
  order: string[]; labels: Record<string, string>; currentStage: string;
}) {
  const currentIndex = order.indexOf(currentStage);
  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
      {order.map((key, i) => {
        const done = i <= currentIndex;
        const running = i === currentIndex;
        return (
          <div key={key} style={{
            flex: "1 1 100px", minWidth: 100, borderRadius: 10, padding: "10px 12px",
            border: "1px solid var(--line)", background: done ? "var(--ok-bg)" : "var(--ice)",
          }}>
            <div style={{
              width: 22, height: 22, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 11, fontWeight: 700, marginBottom: 6,
              background: done ? "var(--ok)" : "var(--line)", color: done ? "#fff" : "var(--muted)",
            }}>
              {done ? "✓" : i + 1}
            </div>
            <div style={{ fontSize: 12.5, fontWeight: 600 }}>{labels[key]}</div>
            <div style={{ fontSize: 10.5, color: "var(--muted)", marginTop: 2 }}>
              {running && !done ? "current" : done ? "done" : "waiting"}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function ExtractionPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const requestId = params.id;

  const [me, setMe] = useState<Me | null>(null);
  const [checking, setChecking] = useState(true);
  const [data, setData] = useState<Extraction | null>(null);
  const [notQueued, setNotQueued] = useState(false);
  const [selectedTwinId, setSelectedTwinId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | "business" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

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
    const res = await fetch(`/api/requests/${requestId}/extraction`);
    if (!res.ok) { setNotQueued(true); return; }
    const d: Extraction = await res.json();
    setData(d);
    setSelectedTwinId(prev => (prev !== null ? prev : (d.documentTwins[0]?.id ?? null)));
  }, [requestId]);

  useEffect(() => { if (me) load(); }, [me, load]);

  const advanceTwin = async (twinId: number) => {
    setActionError(null);
    setBusyId(twinId);
    try {
      const res = await fetch(`/api/requests/${requestId}/extraction/${twinId}/advance`, { method: "POST" });
      const d = await res.json();
      if (!res.ok) { setActionError(d.error || "Could not advance this document twin."); return; }
      await load();
    } finally {
      setBusyId(null);
    }
  };

  const advanceBusinessTwin = async () => {
    setActionError(null);
    setBusyId("business");
    try {
      const res = await fetch(`/api/requests/${requestId}/business-twin/advance`, { method: "POST" });
      const d = await res.json();
      if (!res.ok) { setActionError(d.error || "Could not advance the business twin."); return; }
      await load();
    } finally {
      setBusyId(null);
    }
  };

  if (checking || !me) return null;

  const selected = data?.documentTwins.find(t => t.id === selectedTwinId) ?? null;

  return (
    <div className="dash-page">
      <div className="topbar2">
        <span className="name">Credit File Server 2.0</span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
          <button className="btn ghost" onClick={() => router.push(`/parking-bay/${requestId}`)}>Back to parking bay</button>
        </div>
      </div>

      <div className="dash">
        {notQueued && <p className="formnote">Extraction hasn&apos;t been kicked off yet for this request.</p>}
        {!notQueued && !data && <p style={{ color: "var(--muted)" }}>Loading…</p>}

        {data && (
          <>
            <div className="dhead">
              <h3>Twin extraction — watch it happen</h3>
              <div className="who">{data.referenceNumber && <span>Reference {data.referenceNumber}</span>}</div>
            </div>

            <WorkspaceNav />

            {actionError && <p className="formnote" style={{ marginBottom: 16 }}>{actionError}</p>}

            <div className="panel" style={{ display: "flex", gap: 20, padding: 0, overflow: "hidden" }}>
              <aside style={{ width: 260, flexShrink: 0, borderRight: "1px solid var(--line)", background: "var(--ice)" }}>
                <div style={{ padding: "14px 16px", fontSize: 12, fontWeight: 600, color: "var(--muted)", borderBottom: "1px solid var(--line)" }}>
                  Documents queued · {data.documentTwins.length}
                </div>
                {data.documentTwins.map(t => (
                  <div key={t.id} onClick={() => setSelectedTwinId(t.id)}
                    style={{
                      padding: "12px 16px", borderBottom: "1px solid var(--line-soft)", cursor: "pointer",
                      background: t.id === selectedTwinId ? "var(--navy-100)" : "transparent",
                    }}>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{t.fileName}</div>
                    <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
                      {DOCUMENT_STAGE_LABELS[t.currentStage]} · {t.overallPercent}%
                    </div>
                  </div>
                ))}
              </aside>

              <div style={{ flex: 1, minWidth: 0, padding: "18px 20px" }}>
                {!selected && <p style={{ color: "var(--muted)", fontSize: 13.5 }}>No documents were queued for extraction.</p>}
                {selected && (
                  <>
                    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
                      <h4 style={{ fontFamily: "var(--display)", color: "var(--navy)", fontSize: 15 }}>{selected.fileName}</h4>
                      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
                        <span style={{ color: "var(--muted)" }}>Overall</span>
                        <div style={{ width: 100, height: 6, borderRadius: 999, background: "var(--line)", overflow: "hidden" }}>
                          <div style={{ width: `${selected.overallPercent}%`, height: "100%", background: "var(--gold)" }} />
                        </div>
                        <b style={{ color: "var(--navy)" }}>{selected.overallPercent}%</b>
                      </div>
                    </div>

                    <div style={{ marginBottom: 20 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                        <h5 style={{ fontSize: 13 }}>Document twin</h5>
                        <span className="badge warn">Stage {DOCUMENT_STAGE_ORDER.indexOf(selected.currentStage) + 1} of {DOCUMENT_STAGE_ORDER.length}</span>
                        {selected.classificationLabel && <span className="badge info">{selected.classificationLabel}</span>}
                      </div>
                      <StageTrack order={DOCUMENT_STAGE_ORDER} labels={DOCUMENT_STAGE_LABELS} currentStage={selected.currentStage} />
                      <button className="btn primary" style={{ marginTop: 12 }}
                        disabled={busyId === selected.id || DOCUMENT_STAGE_ORDER.indexOf(selected.currentStage) === DOCUMENT_STAGE_ORDER.length - 1}
                        onClick={() => advanceTwin(selected.id)}>
                        {DOCUMENT_STAGE_ORDER.indexOf(selected.currentStage) === DOCUMENT_STAGE_ORDER.length - 1
                          ? "Document twin complete"
                          : `Advance to ${DOCUMENT_STAGE_LABELS[DOCUMENT_STAGE_ORDER[DOCUMENT_STAGE_ORDER.indexOf(selected.currentStage) + 1]]}`}
                      </button>

                      {selected.extractedValues.length > 0 && (
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, marginTop: 14 }}>
                          <thead>
                            <tr style={{ textAlign: "left", color: "var(--muted)", fontSize: 11 }}>
                              <th style={{ padding: "5px 8px" }}>Field</th>
                              <th style={{ padding: "5px 8px" }}>Value</th>
                              <th style={{ padding: "5px 8px" }}>Source</th>
                              <th style={{ padding: "5px 8px" }}>Confidence</th>
                              <th style={{ padding: "5px 8px" }}>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selected.extractedValues.map(v => (
                              <tr key={v.id} style={{ borderTop: "1px solid var(--line-soft)" }}>
                                <td style={{ padding: "6px 8px" }}>{v.fieldName}</td>
                                <td style={{ padding: "6px 8px" }}><b>{v.value}</b></td>
                                <td style={{ padding: "6px 8px", color: "var(--muted)" }}>{v.source}</td>
                                <td style={{ padding: "6px 8px" }}>{Math.round(v.confidence * 100)}%</td>
                                <td style={{ padding: "6px 8px" }}>
                                  <span className={v.needsReview ? "badge warn" : "badge ok"}>{v.needsReview ? "HITL review" : "Verified"}</span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                      {DOCUMENT_STAGE_ORDER.indexOf(selected.currentStage) >= DOCUMENT_STAGE_ORDER.indexOf("extracted") && selected.extractedValues.length === 0 && (
                        <p style={{ fontSize: 12, color: "var(--muted)", marginTop: 12 }}>No extractable values found in this file.</p>
                      )}
                    </div>

                    {data.businessTwin && (
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                          <h5 style={{ fontSize: 13 }}>Business twin</h5>
                          <span className="badge info">Stage {BUSINESS_STAGE_ORDER.indexOf(data.businessTwin.currentStage) + 1} of {BUSINESS_STAGE_ORDER.length}</span>
                        </div>
                        <StageTrack order={BUSINESS_STAGE_ORDER} labels={BUSINESS_STAGE_LABELS} currentStage={data.businessTwin.currentStage} />
                        <button className="btn ghost" style={{ marginTop: 12 }}
                          disabled={busyId === "business" || BUSINESS_STAGE_ORDER.indexOf(data.businessTwin.currentStage) === BUSINESS_STAGE_ORDER.length - 1}
                          onClick={advanceBusinessTwin}>
                          {BUSINESS_STAGE_ORDER.indexOf(data.businessTwin.currentStage) === BUSINESS_STAGE_ORDER.length - 1
                            ? "Business twin complete"
                            : `Advance to ${BUSINESS_STAGE_LABELS[BUSINESS_STAGE_ORDER[BUSINESS_STAGE_ORDER.indexOf(data.businessTwin.currentStage) + 1]]}`}
                        </button>
                        <p style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 8 }}>
                          Covenant ledger onward needs every queued document to reach Extracted first.
                        </p>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>

            <div className="panel" style={{ marginTop: 20 }}>
              <div className="phead"><h4>Live extraction log</h4><span className="note">{data.log.length} events</span></div>
              <div style={{ background: "var(--ink)", borderRadius: 10, padding: 14, maxHeight: 260, overflowY: "auto", fontFamily: "monospace", fontSize: 12 }}>
                {data.log.length === 0 && <div style={{ color: "#8b93a8" }}>No events yet.</div>}
                {data.log.map((e, i) => (
                  <div key={i} style={{ color: "#d7dcea", marginBottom: 3 }}>
                    <span style={{ color: "#8b93a8" }}>{new Date(e.at).toLocaleTimeString()}</span>{"  "}
                    <span style={{ color: "#e8b969" }}>{e.type}</span>
                    {e.detail && <span>{"  "}{e.detail}</span>}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
