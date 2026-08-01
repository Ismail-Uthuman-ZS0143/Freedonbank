"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import WorkspaceNav from "../components/WorkspaceNav";

interface Me { id: number; email: string; fullName: string; isStaff: boolean; }

interface ActivityEvent { type: "bank" | "customer" | "system" | "alert"; title: string; detail: string; at: string; }
interface ActivityRequest {
  id: number; borrowerName: string; companyName: string; referenceNumber: string | null;
  status: string; events: ActivityEvent[];
}

const EVENT_DOT: Record<string, string> = {
  bank: "var(--navy)", customer: "var(--gold)", system: "var(--muted)", alert: "var(--bad)",
};

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  sent: { label: "Sent · link active", className: "badge info" },
  uploads_complete: { label: "Uploads complete", className: "badge ok" },
  expired: { label: "Link expired", className: "badge warn" },
  fraud_stopped: { label: "Session ended — fraud guard", className: "badge bad" },
};

function initials(name: string) {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

export default function CustomerActivityPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [checking, setChecking] = useState(true);
  const [requests, setRequests] = useState<ActivityRequest[] | null>(null);

  useEffect(() => {
    fetch("/api/auth/me")
      .then(r => r.json())
      .then(d => {
        if (!d.user) { router.replace("/"); return; }
        setMe(d.user);
      })
      .finally(() => setChecking(false));
  }, [router]);

  useEffect(() => {
    if (!me) return;
    fetch("/api/requests/activity").then(r => r.json()).then(d => setRequests(d.requests));
  }, [me]);

  if (checking || !me) return null;

  return (
    <div className="dash-page">
      <div className="topbar2">
        <span className="name">Credit File Server 2.0</span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
          <span>{me.fullName}</span>
        </div>
      </div>

      <div className="dash">
        <div className="dhead">
          <h3>Customer activity</h3>
          <div className="who">Every request, one real event trail each <span className="avatar">{initials(me.fullName)}</span></div>
        </div>

        <WorkspaceNav activeCount={requests?.filter(r => r.status === "sent").length} />

        <div style={{ display: "flex", gap: 16, marginBottom: 20, fontSize: 12.5, color: "var(--muted)" }}>
          {(["bank", "customer", "system", "alert"] as const).map(t => (
            <span key={t} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: EVENT_DOT[t], display: "inline-block" }} />
              {t === "bank" ? "Bank action" : t === "customer" ? "Customer action" : t === "system" ? "System · twin" : "Alert"}
            </span>
          ))}
        </div>

        {!requests && <p style={{ color: "var(--muted)" }}>Loading…</p>}
        {requests?.length === 0 && <p style={{ color: "var(--muted)", fontSize: 13.5 }}>No activity yet.</p>}

        {requests?.map(r => {
          const badge = STATUS_BADGE[r.status] ?? { label: r.status, className: "badge info" };
          return (
            <div className="panel" key={r.id} style={{ marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
                <span className="avatar" style={{ width: 32, height: 32, fontSize: 12 }}>{initials(r.borrowerName)}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <b>{r.borrowerName}</b>
                  <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
                    {r.companyName}
                    {r.referenceNumber && <> · {r.referenceNumber}</>}
                  </div>
                </div>
                <span className={badge.className}>{badge.label}</span>
                <button className="btn ghost" onClick={() => router.push(`/parking-bay/${r.id}`)}>Open</button>
              </div>

              {r.events.length === 0 && <p style={{ fontSize: 12.5, color: "var(--muted)" }}>No events logged yet.</p>}
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {r.events.map((e, i) => (
                  <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start", fontSize: 13 }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: EVENT_DOT[e.type], marginTop: 5, flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <span style={{ fontWeight: 600 }}>{e.title}</span>
                      {e.detail && <span style={{ color: "var(--muted)" }}> · {e.detail}</span>}
                    </div>
                    <span style={{ fontSize: 11.5, color: "var(--muted)", whiteSpace: "nowrap" }}>
                      {new Date(e.at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
