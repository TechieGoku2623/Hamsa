import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Logo } from "../App";
import { api, ApiError, type User } from "../lib/api";
import { useSession } from "../session";

export default function LoginPage() {
  const { signIn, user } = useSession();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next") || "/";
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [devCode, setDevCode] = useState<string | null>(null);
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [adult, setAdult] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function requestCode(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ phone: string; dev_code?: string }>("/auth/otp/request", { body: { phone } });
      setPhone(r.phone);
      setDevCode(r.dev_code ?? null);
      setStep("code");
    } catch (err) {
      setError(err instanceof ApiError ? String(err.message) : "Could not send code");
    } finally {
      setBusy(false);
    }
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ token: string; user: User }>("/auth/otp/verify", {
        body: { phone, code, display_name: name.trim() || user?.display_name || "" },
      });
      signIn(r.token, r.user);
      nav(next, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? String(err.message) : "Could not verify");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <div className="auth-card">
        <Logo />
        <h1>Private chats. Shops that reply instantly.</h1>
        <p className="muted">Personal and group chats are end-to-end encrypted. Order from local shops, pay by UPI.</p>
        {step === "phone" ? (
          <form onSubmit={requestCode} className="stack">
            <label>
              Mobile number
              <div className="phone-input">
                <span>+91</span>
                <input autoFocus inputMode="tel" placeholder="98765 43210" value={phone} onChange={(e) => setPhone(e.target.value)} required />
              </div>
            </label>
            <label>
              Your name
              <input placeholder="Asha" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
            </label>
            <label className="check">
              <input type="checkbox" checked={adult} onChange={(e) => setAdult(e.target.checked)} required />
              I am 18 or older
            </label>
            <button className="primary" disabled={busy || !adult}>{busy ? "Sending…" : "Send code"}</button>
          </form>
        ) : (
          <form onSubmit={verify} className="stack">
            <label>
              Enter the 6-digit code sent to {phone}
              <input autoFocus inputMode="numeric" pattern="\d{6}" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} required />
            </label>
            {devCode && <p className="hint">Development build: your code is <b>{devCode}</b></p>}
            <button className="primary" disabled={busy}>{busy ? "Verifying…" : "Verify"}</button>
            <button type="button" className="link" onClick={() => setStep("phone")}>Change number</button>
          </form>
        )}
        {error && <p className="error">{error}</p>}
      </div>
    </div>
  );
}
