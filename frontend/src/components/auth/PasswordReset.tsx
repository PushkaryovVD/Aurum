import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "@/lib/i18n";
import { sessionTransportAllowed, type AppAuthStatus } from "@/lib/appAuth";
import { entryButton, entryControl } from "./EntryFrame";

const RESET_PATH = "/reset-password";
const TOKEN_HASH_PREFIX = "#token=";

/** Reads the token from an e-mailed `/reset-password#token=…` link once and
 * removes it from the address bar. The fragment never reaches the server or
 * proxy logs; the token is posted only when the new password is submitted. */
export function takeResetTokenFromLocation(): string | null {
  const { hash, pathname } = window.location;
  if (pathname !== RESET_PATH || !hash.startsWith(TOKEN_HASH_PREFIX)) return null;
  const token = decodeURIComponent(hash.slice(TOKEN_HASH_PREFIX.length)).trim();
  window.history.replaceState(window.history.state, "", RESET_PATH);
  return token || null;
}

const primaryButton = `${entryButton} w-full bg-text-primary text-surface-1 hover:bg-text-secondary`;

/** Step 1: ask for a reset link. The reply is the same whether or not the
 * account exists, so this screen never confirms that a login is registered. */
export function PasswordResetRequest({ status, onBack }: { status: AppAuthStatus; onBack: () => void }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [state, setState] = useState<"idle" | "sent" | "limited" | "error">("idle");
  const allowed = sessionTransportAllowed(status, window.location);
  const enabled = allowed && !busy && state !== "sent";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!enabled) return;
    const identifier = String(new FormData(event.currentTarget).get("identifier") ?? "").trim();
    if (!identifier) return;
    setBusy(true);
    try {
      const response = await fetch("/api/auth/password-reset/request", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ identifier }),
      });
      setState(response.status === 202 ? "sent" : response.status === 429 ? "limited" : "error");
    } catch {
      setState("error");
    } finally { setBusy(false); }
  }

  return <>
    <h2 className="text-xl font-semibold tracking-tight">{t("entry.resetTitle")}</h2>
    <p className="mt-4 text-sm leading-relaxed text-text-secondary">{t("entry.resetIntro")}</p>
    {!allowed && <p className="mt-5 text-sm text-warning" role="alert">{t("entry.transport")}</p>}
    {state === "sent" && <p className="mt-5 rounded-lg border border-success/30 bg-success/10 p-3 text-sm text-success" role="status">{t("entry.resetSent")}</p>}
    {state === "limited" && <p className="mt-5 text-sm text-danger" role="alert">{t("entry.inviteLimited")}</p>}
    {state === "error" && <p className="mt-5 text-sm text-danger" role="alert">{t("entry.resetRequestError")}</p>}
    <form className="mt-6 space-y-4" onSubmit={(event) => void submit(event)} aria-busy={busy}>
      <label className="block text-sm" htmlFor="reset-identifier">{t("entry.identifier")}<input id="reset-identifier" name="identifier" type="email" inputMode="email" autoComplete="username" required maxLength={320} disabled={!enabled} className={`${entryControl} mt-2 w-full`} /></label>
      <button type="submit" disabled={!enabled} className={primaryButton}>{busy ? t("entry.resetSending") : t("entry.resetSend")}</button>
    </form>
    <button type="button" disabled={busy} className={`${entryButton} mt-3 w-full`} onClick={onBack}>{t("entry.inviteBack")}</button>
  </>;
}

/** Step 2: the page opened from the e-mailed link. */
export function PasswordResetConfirm({ status, token, onDone }: { status: AppAuthStatus; token: string; onDone: () => void }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [state, setState] = useState<"idle" | "done" | "mismatch" | "weak" | "invalid" | "limited" | "error">("idle");
  const formRef = useRef<HTMLFormElement>(null);
  const allowed = sessionTransportAllowed(status, window.location);
  const enabled = allowed && !busy && state !== "done" && state !== "invalid";

  function clearPasswords() {
    formRef.current?.reset();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!enabled) return;
    const values = new FormData(event.currentTarget);
    const password = String(values.get("password") ?? "");
    const repeat = String(values.get("password_repeat") ?? "");
    if (password !== repeat) { setState("mismatch"); return; }
    if (password.length < 12) { setState("weak"); return; }
    setBusy(true);
    try {
      const response = await fetch("/api/auth/password-reset/confirm", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });
      clearPasswords();
      setState(response.status === 204 ? "done"
        : response.status === 422 ? "weak"
        : response.status === 429 ? "limited"
        : response.status === 400 ? "invalid" : "error");
    } catch {
      setState("error");
    } finally { setBusy(false); }
  }

  const messages = {
    mismatch: "entry.resetMismatch",
    weak: "entry.invitePasswordHint",
    invalid: "entry.resetInvalid",
    limited: "entry.inviteLimited",
    error: "entry.inviteNetwork",
  } as const;

  return <>
    <h2 className="text-xl font-semibold tracking-tight">{t("entry.resetNewTitle")}</h2>
    {!allowed && <p className="mt-5 text-sm text-warning" role="alert">{t("entry.transport")}</p>}
    {state === "done" ? <>
      <p className="mt-5 rounded-lg border border-success/30 bg-success/10 p-3 text-sm text-success" role="status">{t("entry.resetDone")}</p>
      <button type="button" className={`${primaryButton} mt-5`} onClick={onDone}>{t("entry.signIn")}</button>
    </> : <>
      <p className="mt-4 text-sm leading-relaxed text-text-secondary">{t("entry.resetNewIntro")}</p>
      {state !== "idle" && <p className="mt-5 text-sm text-danger" role="alert">{t(messages[state])}</p>}
      <form ref={formRef} className="mt-6 space-y-4" onSubmit={(event) => void submit(event)} aria-busy={busy}>
        <label className="block text-sm" htmlFor="reset-password">{t("entry.resetNewPassword")}<input id="reset-password" name="password" type="password" autoComplete="new-password" required minLength={12} maxLength={1024} disabled={!enabled} className={`${entryControl} mt-2 w-full`} /><span className="mt-1 block text-xs text-text-muted">{t("entry.invitePasswordHint")}</span></label>
        <label className="block text-sm" htmlFor="reset-password-repeat">{t("entry.resetRepeat")}<input id="reset-password-repeat" name="password_repeat" type="password" autoComplete="new-password" required minLength={12} maxLength={1024} disabled={!enabled} className={`${entryControl} mt-2 w-full`} /></label>
        <button type="submit" disabled={!enabled} className={primaryButton}>{busy ? t("entry.resetSaving") : t("entry.resetSave")}</button>
      </form>
      <button type="button" disabled={busy} className={`${entryButton} mt-3 w-full`} onClick={onDone}>{t("entry.inviteBack")}</button>
    </>}
  </>;
}
