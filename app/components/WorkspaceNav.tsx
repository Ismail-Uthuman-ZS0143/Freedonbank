"use client";

import { usePathname, useRouter } from "next/navigation";

// The v5 mockup also shows Loans / Portfolio tabs here, but those need
// pipeline stages (Credit review, Term sheet, etc.) that aren't built in
// this project -- omitted rather than linked to something fake.
const TABS = [
  { href: "/dashboard", label: "Overview" },
  { href: "/activity", label: "Customer activity" },
  { href: "/parking-bay", label: "Parking bay" },
];

export default function WorkspaceNav({ activeCount }: { activeCount?: number }) {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <nav aria-label="Workspace" style={{ display: "flex", gap: 4, marginBottom: 22, borderBottom: "1px solid var(--line)" }}>
      {TABS.map(tab => {
        const active = pathname === tab.href || (tab.href === "/parking-bay" && pathname?.startsWith("/parking-bay/"));
        return (
          <button key={tab.href} onClick={() => router.push(tab.href)}
            style={{
              padding: "10px 16px", fontSize: 13.5, fontWeight: 600, border: "none", background: "none", cursor: "pointer",
              color: active ? "var(--navy)" : "var(--muted)",
              borderBottom: active ? "2px solid var(--navy)" : "2px solid transparent",
              marginBottom: -1,
            }}>
            {tab.label}
            {tab.href === "/activity" && typeof activeCount === "number" && activeCount > 0 && (
              <span style={{ marginLeft: 7, fontSize: 11, fontWeight: 700, background: "var(--navy-100)", color: "var(--navy)", borderRadius: 999, padding: "1px 7px" }}>
                {activeCount}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
