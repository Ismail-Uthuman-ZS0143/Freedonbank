"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

export default function SignInPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    fetch("/api/auth/me")
      .then(r => r.json())
      .then(d => { if (d.user) router.replace("/dashboard"); })
      .catch(() => {})
      .finally(() => setChecking(false));
  }, [router]);

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Sign-in failed.");
        return;
      }
      router.replace("/dashboard");
    } catch {
      setError("Could not reach the sign-in service — is the backend running?");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSSO = () => {
    setNote("Bank SSO isn't wired up yet.");
  };

  if (checking) return null;

  return (
    <div className="login-page">
      <div className="login">
        <div className="side">
          <span aria-hidden="true">
            <svg width="46" height="46" viewBox="0 0 34 34">
              <circle cx="17" cy="17" r="12.5" fill="none" stroke="#3A4D96" strokeWidth="5" />
              <path d="M17 4.5 A12.5 12.5 0 0 1 29.5 17" fill="none" stroke="#E87722" strokeWidth="5" strokeLinecap="round" />
            </svg>
          </span>
          <div className="tagline">&quot;Every document understood. Every relationship seen whole.&quot;</div>
          <div className="sub">Credit File Server 2.0</div>
        </div>

        <form className="form" onSubmit={handleSignIn}>
          <h3>Sign in to your workspace</h3>
          <p className="lsub">Freedom Bank of Virginia · commercial banking</p>

          <div className="field">
            <label htmlFor="lg-email">Work email</label>
            <input
              id="lg-email"
              type="email"
              required
              placeholder="d.whitfield@freedombankva.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="lg-pass">Password</label>
            <input
              id="lg-pass"
              type="password"
              required
              placeholder="••••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
            />
          </div>

          {error && <p className="formnote">{error}</p>}
          {note && <p className="formnote">{note}</p>}

          <button type="submit" className="btn primary" style={{ width: "100%" }} disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </button>
          <div className="divider">or</div>
          <button type="button" className="btn ghost" style={{ width: "100%" }} onClick={handleSSO}>
            Continue with bank SSO
          </button>
          <div className="mfa">🛡️ Multi-factor authentication required on every session</div>
        </form>
      </div>
    </div>
  );
}
