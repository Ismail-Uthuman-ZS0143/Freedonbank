"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import WorkspaceNav from "../components/WorkspaceNav";

interface Me { id: number; email: string; fullName: string; isStaff: boolean; }

interface ParkingBayRow {
  id: number; borrowerName: string; companyName: string; referenceNumber: string | null;
  totalCount: number; approvedCount: number; flaggedCount: number; pendingCount: number;
  reviewComplete: boolean;
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

export default function ParkingBayListPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [checking, setChecking] = useState(true);
  const [rows, setRows] = useState<ParkingBayRow[] | null>(null);

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
    fetch("/api/requests/parking-bay").then(r => r.json()).then(d => setRows(d.requests));
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
          <h3>Parking bay</h3>
          <div className="who">Every request with documents awaiting review <span className="avatar">{initials(me.fullName)}</span></div>
        </div>

        <WorkspaceNav />

        {!rows && <p style={{ color: "var(--muted)" }}>Loading…</p>}
        {rows?.length === 0 && (
          <p style={{ color: "var(--muted)", fontSize: 13.5 }}>Nothing waiting on review right now — the parking bay is empty.</p>
        )}

        {rows?.map(r => (
          <div className="panel" key={r.id} style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 14 }}>
            <span className="avatar" style={{ width: 32, height: 32, fontSize: 12, flexShrink: 0 }}>{initials(r.borrowerName)}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <b>{r.borrowerName}</b>
              <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
                {r.companyName}
                {r.referenceNumber && <> · {r.referenceNumber}</>}
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
              {r.pendingCount > 0 && <span className="badge info">{r.pendingCount} pending review</span>}
              {r.approvedCount > 0 && <span className="badge ok">{r.approvedCount} approved</span>}
              {r.flaggedCount > 0 && <span className="badge warn">{r.flaggedCount} flagged</span>}
              {r.reviewComplete && <span className="badge ok">Ready for extraction</span>}
            </div>
            <button className="btn ghost" onClick={() => router.push(`/parking-bay/${r.id}`)}>Open</button>
          </div>
        ))}
      </div>
    </div>
  );
}
