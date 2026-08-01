"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

interface Me { id: number; email: string; fullName: string; isStaff: boolean; }
interface TemplateItem { name: string; audience: "lender" | "loan_admin"; selected: boolean; }
interface TemplateCategory { category: string; items: TemplateItem[]; }
interface ChecklistTemplate { categories: TemplateCategory[]; }
interface PreferenceItem { category: string; name: string; }

function key(category: string, name: string) {
  return `${category}::${name}`;
}

export default function ChecklistSettingsPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [checking, setChecking] = useState(true);

  const [template, setTemplate] = useState<ChecklistTemplate | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [isSaved, setIsSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);

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
    Promise.all([
      fetch("/api/requests/checklist-template").then(r => r.json()) as Promise<ChecklistTemplate>,
      fetch("/api/requests/checklist-preference").then(r => r.json()) as Promise<{ selectedItems: PreferenceItem[]; isSaved: boolean }>,
    ]).then(([tmpl, pref]) => {
      setTemplate(tmpl);
      setSelected(new Set(pref.selectedItems.map(i => key(i.category, i.name))));
      setIsSaved(pref.isSaved);
    });
  }, [me]);

  const toggle = (category: string, name: string) => {
    setJustSaved(false);
    setSelected(prev => {
      const next = new Set(prev);
      const k = key(category, name);
      if (next.has(k)) next.delete(k); else next.add(k);
      return next;
    });
  };

  const allItems = template?.categories.flatMap(c => c.items.map(i => ({ ...i, category: c.category }))) ?? [];
  const selectedItems = allItems.filter(i => selected.has(key(i.category, i.name)));
  const lenderCount = selectedItems.filter(i => i.audience === "lender").length;
  const loanAdminCount = selectedItems.filter(i => i.audience === "loan_admin").length;

  const handleSave = async () => {
    setSaveError(null);
    setSaving(true);
    try {
      const res = await fetch("/api/requests/checklist-preference", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ selectedItems: selectedItems.map(i => ({ category: i.category, name: i.name })) }),
      });
      const data = await res.json();
      if (!res.ok) {
        setSaveError(data.error || "Could not save your checklist.");
        return;
      }
      setIsSaved(true);
      setJustSaved(true);
    } finally {
      setSaving(false);
    }
  };

  if (checking || !me) return null;

  return (
    <div className="dash-page">
      <div className="topbar2">
        <span className="name">Credit File Server 2.0</span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
          <span>{me.fullName}</span>
          <button className="btn ghost" onClick={() => router.push("/dashboard")}>Back to dashboard</button>
        </div>
      </div>

      <div className="dash">
        <div className="dhead">
          <h3>Profile settings — document checklist</h3>
          <div className="who">Settings › <b style={{ color: "var(--navy)" }}>Document checklist</b></div>
        </div>

        <div className="panel">
          <div className="phead">
            <h4>Default document checklist</h4>
            <span className="note">{isSaved ? "Saved to your profile" : "Using the standard default — not yet saved"}</span>
          </div>
          <p style={{ fontSize: 12.5, color: "var(--muted)", marginBottom: 14 }}>
            Set once here — every <b>Send secure request</b> on the dashboard uses this list, not rebuilt per
            request. Selected items join the internal checklist either way — but only &quot;Lender&quot; items are ever
            shown to the customer through the link; &quot;Loan Admin&quot; items stay internal.
          </p>
          <div style={{ display: "flex", gap: 8, marginBottom: 18, flexWrap: "wrap" }}>
            <span className="badge info">{selectedItems.length} selected</span>
            <span className="badge ok">{lenderCount} customer-facing · Lender</span>
            <span className="badge warn">{loanAdminCount} internal · Loan Admin</span>
          </div>

          {!template && <p style={{ color: "var(--muted)" }}>Loading…</p>}
          {template?.categories.map(cat => (
            <div key={cat.category} style={{ marginBottom: 18 }}>
              <h6 style={{ fontSize: 12, fontWeight: 600, color: "var(--navy)", marginBottom: 8 }}>{cat.category}</h6>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 18px" }}>
                {cat.items.map(item => {
                  const k = key(cat.category, item.name);
                  return (
                    <label key={k} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, minWidth: 260 }}>
                      <input type="checkbox" checked={selected.has(k)} onChange={() => toggle(cat.category, item.name)} />
                      <span>{item.name}</span>
                      <span className={item.audience === "lender" ? "badge ok" : "badge warn"} style={{ fontSize: 9.5, padding: "2px 6px" }}>
                        {item.audience === "lender" ? "Lender" : "Loan Admin"}
                      </span>
                    </label>
                  );
                })}
              </div>
            </div>
          ))}

          {saveError && <p className="formnote" style={{ marginBottom: 14 }}>{saveError}</p>}
          <div className="factions">
            <button className="btn navy" disabled={saving || selectedItems.length === 0} onClick={handleSave}>
              {saving ? "Saving…" : "Save configuration"}
            </button>
            {justSaved && <span className="note" style={{ color: "var(--ok)" }}>Saved — future requests will use this list.</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
