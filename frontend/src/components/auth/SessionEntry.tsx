import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { sessionTransportAllowed, type AppAuthStatus } from "@/lib/appAuth";
import { entryButton, entryControl } from "./EntryFrame";

interface IdentitySession {
  user: { id: string; identifier: string; display_name: string };
  csrf_token: string;
}
function parseSession(value: unknown): IdentitySession {
  const data = value as Partial<IdentitySession> | null;
  if (!data || !data.user || typeof data.user.id !== "string" || !data.user.id ||
      typeof data.user.identifier !== "string" || typeof data.user.display_name !== "string" ||
      typeof data.csrf_token !== "string" || !data.csrf_token) throw new Error("Invalid identity session");
  // Only identity and CSRF enter memory; workspace data is deliberately unused.
  return { user: data.user, csrf_token: data.csrf_token };
}
async function currentSession(signal: AbortSignal): Promise<IdentitySession | null> {
  const response = await fetch("/api/auth/me", { credentials: "same-origin", cache: "no-store", signal });
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("Session verification failed");
  return parseSession(await response.json());
}

/** Identity-only session entry. No financial query or workspace switch exists here. */
export function SessionEntry({
  status,
  onFinanceAccessGranted,
}: {
  status: AppAuthStatus;
  onFinanceAccessGranted: () => void;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const allowed = sessionTransportAllowed(status, window.location);
  const [session, setSession] = useState<IdentitySession | null>(null);
  const [phase, setPhase] = useState<"checking" | "anonymous" | "session" | "error">("checking");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<"entry.sessionError" | "entry.loginError" | "entry.limited" | "entry.logoutError" | null>(null);
  const [attempt, setAttempt] = useState(0);
  const pending = useRef<AbortController | null>(null);
  const busyRef = useRef(false);

  useEffect(() => {
    const controller = new AbortController(); pending.current = controller;
    setPhase("checking"); setSession(null); setMessage(null);
    // Clear any legacy finance cache when entering explicitly required mode.
    void client.cancelQueries().then(() => client.clear());
    if (allowed) void currentSession(controller.signal).then((value) => {
      if (!controller.signal.aborted) {
        setSession(value);
        setPhase(value ? "session" : "anonymous");
        if (value && status.finance_access_ready) onFinanceAccessGranted();
      }
    }).catch(() => { if (!controller.signal.aborted) { setPhase("error"); setMessage("entry.sessionError"); } });
    return () => { controller.abort(); pending.current?.abort(); };
  }, [allowed, attempt, client, onFinanceAccessGranted, status.finance_access_ready]);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!allowed || !status.app_auth_required || phase !== "anonymous" || busyRef.current) return;
    const form = event.currentTarget;
    const fields = new FormData(form);
    const identifier = String(fields.get("identifier") ?? "");
    const password = String(fields.get("password") ?? "");
    form.reset();
    if (!identifier || !password) return;
    const controller = new AbortController(); pending.current?.abort(); pending.current = controller;
    busyRef.current = true; setBusy(true); setMessage(null);
    try {
      // Existing backend contract is POST/DELETE /auth/session, not /login or /logout.
      const response = await fetch("/api/auth/session", {
        method: "POST", credentials: "same-origin", cache: "no-store", signal: controller.signal,
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ identifier, password }),
      });
      if (!response.ok) {
        if (!controller.signal.aborted) setMessage(response.status === 429 ? "entry.limited" : "entry.loginError");
        return;
      }
      parseSession(await response.json());
      // A successful body alone does not prove the browser accepted the cookie.
      const verified = await currentSession(controller.signal);
      if (!verified) throw new Error("Cookie session not established");
      await client.cancelQueries(); client.clear();
      if (!controller.signal.aborted) {
        setSession(verified);
        setPhase("session");
        if (status.finance_access_ready) onFinanceAccessGranted();
      }
    } catch {
      if (!controller.signal.aborted) { setSession(null); setPhase("error"); setMessage("entry.sessionError"); }
    } finally {
      busyRef.current = false;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  async function signOut() {
    if (!session || !allowed || busyRef.current) return;
    const controller = new AbortController(); pending.current?.abort(); pending.current = controller;
    busyRef.current = true; setBusy(true); setMessage(null);
    await client.cancelQueries(); client.clear();
    try {
      const response = await fetch("/api/auth/session", {
        method: "DELETE", credentials: "same-origin", cache: "no-store", signal: controller.signal,
        headers: { "X-CSRF-Token": session.csrf_token },
      });
      if (!response.ok && response.status !== 401) throw new Error("Logout failed");
      const verified = await currentSession(controller.signal);
      if (verified) throw new Error("Session still active");
      if (!controller.signal.aborted) { setSession(null); setPhase("anonymous"); }
    } catch {
      if (!controller.signal.aborted) setMessage("entry.logoutError");
    } finally {
      busyRef.current = false;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  const enabled = allowed && phase === "anonymous" && !busy;
  return <>
    <h2 className="text-xl font-semibold tracking-tight">{t("entry.title")}</h2>
    <div className="mt-5 rounded-xl border border-border bg-surface-0 p-4"><h3 className="font-medium">{t("entry.blocked")}</h3><p className="mt-2 text-sm leading-relaxed text-text-secondary">{t("entry.blockedBody")}</p></div>
    {!allowed && <p className="mt-5 text-sm text-warning" role="alert">{t("entry.transport")}</p>}
    {allowed && phase === "checking" && <p className="mt-5" role="status">{t("entry.signingIn")}</p>}
    {message && <p className="mt-5 text-sm text-danger" role="alert">{t(message)}</p>}
    {phase === "session" && session ? <section className="mt-6" aria-live="polite"><p className="font-medium">{t("entry.session")}</p><p className="mt-2 break-words text-text-secondary">{session.user.display_name || session.user.identifier}</p><button type="button" disabled={busy} onClick={() => void signOut()} className={`${entryButton} mt-5 w-full`}>{busy ? t("entry.signingIn") : t("entry.signOut")}</button></section> : <>
      <form className="mt-6 space-y-4" onSubmit={(event) => void signIn(event)} aria-busy={busy}>
        <label className="block text-sm" htmlFor="entry-identifier">{t("entry.identifier")}<input id="entry-identifier" name="identifier" autoComplete="username" required maxLength={320} disabled={!enabled} className={`${entryControl} mt-2 w-full`} /></label>
        <label className="block text-sm" htmlFor="entry-password">{t("entry.password")}<input id="entry-password" name="password" type="password" autoComplete="current-password" required maxLength={1024} disabled={!enabled} className={`${entryControl} mt-2 w-full`} /></label>
        <button type="submit" disabled={!enabled} className={cn(entryButton, "w-full bg-text-primary text-surface-1 hover:bg-text-secondary")}>{busy ? t("entry.signingIn") : t("entry.signIn")}</button>
      </form>
      <p className="mt-5 text-xs leading-relaxed text-text-muted">{t("entry.bootstrap")}</p>
    </>}
    {allowed && (phase === "error" || phase === "session") && <button type="button" disabled={busy} className={`${entryButton} mt-5 w-full`} onClick={() => { setBusy(false); setAttempt(attempt + 1); }}>{t("entry.retry")}</button>}
  </>;
}
