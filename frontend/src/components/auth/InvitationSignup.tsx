import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "@/lib/i18n";
import { sessionTransportAllowed, type AppAuthStatus } from "@/lib/appAuth";
import { entryButton, entryControl } from "./EntryFrame";

const INVITE_HASH_PREFIX = "#invite=";

/** Reads an invitation code from `/login#invite=CODE` once and removes it from
 * the address bar. The fragment is never sent to the server, so the code does
 * not end up in proxy or access logs. */
export function takeInvitationFromHash(): string | null {
  const { hash, pathname, search } = window.location;
  if (!hash.startsWith(INVITE_HASH_PREFIX)) return null;
  const token = decodeURIComponent(hash.slice(INVITE_HASH_PREFIX.length)).trim();
  window.history.replaceState(window.history.state, "", `${pathname}${search}`);
  return token || null;
}

export function invitationLink(token: string): string {
  return `${window.location.origin}/login${INVITE_HASH_PREFIX}${encodeURIComponent(token)}`;
}

/** Account creation for an invited person. It is not public registration: the
 * server accepts it only with a valid one-time invitation bound to this login. */
export function InvitationSignup({ status, initialToken, onComplete, onCancel }: {
  status: AppAuthStatus;
  initialToken: string | null;
  onComplete: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<"entry.inviteError" | "entry.inviteLimited" | "entry.inviteNetwork" | null>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const allowed = sessionTransportAllowed(status, window.location);
  const enabled = allowed && !busy;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!enabled) return;
    const values = new FormData(event.currentTarget);
    const token = String(values.get("token") ?? "").trim();
    const identifier = String(values.get("identifier") ?? "").trim();
    const display_name = String(values.get("display_name") ?? "").trim();
    const password = String(values.get("password") ?? "");
    if (!token || !identifier || !display_name || !password) return;
    setBusy(true); setMessage(null);
    try {
      const response = await fetch("/api/auth/invitations/accept", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, identifier, display_name, password }),
      });
      // The password never stays in the DOM after an attempt.
      const passwordField = formRef.current?.elements.namedItem("password");
      if (passwordField instanceof HTMLInputElement) passwordField.value = "";
      if (response.ok) {
        formRef.current?.reset();
        onComplete();
        return;
      }
      setMessage(response.status === 429 ? "entry.inviteLimited" : "entry.inviteError");
    } catch {
      setMessage("entry.inviteNetwork");
    } finally { setBusy(false); }
  }

  return <>
    <h2 className="text-xl font-semibold tracking-tight">{t("entry.inviteTitle")}</h2>
    <p className="mt-4 text-sm leading-relaxed text-text-secondary">{t("entry.inviteIntro")}</p>
    {!allowed && <p className="mt-5 text-sm text-warning" role="alert">{t("entry.transport")}</p>}
    {message && <p className="mt-5 text-sm text-danger" role="alert">{t(message)}</p>}
    <form ref={formRef} className="mt-6 space-y-4" onSubmit={(event) => void submit(event)} aria-busy={busy}>
      <label className="block text-sm" htmlFor="invite-token">{t("entry.inviteCode")}<input id="invite-token" name="token" type="password" autoComplete="one-time-code" required maxLength={1024} defaultValue={initialToken ?? ""} disabled={!enabled} className={`${entryControl} mt-2 w-full`} /></label>
      <label className="block text-sm" htmlFor="invite-name">{t("entry.bootstrapName")}<input id="invite-name" name="display_name" autoComplete="name" required maxLength={100} disabled={!enabled} className={`${entryControl} mt-2 w-full`} /></label>
      <label className="block text-sm" htmlFor="invite-identifier">{t("entry.identifier")}<input id="invite-identifier" name="identifier" autoComplete="username" required maxLength={320} disabled={!enabled} className={`${entryControl} mt-2 w-full`} /><span className="mt-1 block text-xs text-text-muted">{t("entry.inviteIdentifierHint")}</span></label>
      <label className="block text-sm" htmlFor="invite-password">{t("entry.password")}<input id="invite-password" name="password" type="password" autoComplete="new-password" required minLength={12} maxLength={1024} disabled={!enabled} className={`${entryControl} mt-2 w-full`} /><span className="mt-1 block text-xs text-text-muted">{t("entry.invitePasswordHint")}</span></label>
      <button type="submit" disabled={!enabled} className={`${entryButton} w-full bg-text-primary text-surface-1 hover:bg-text-secondary`}>{busy ? t("entry.inviteSubmitting") : t("entry.inviteSubmit")}</button>
    </form>
    <button type="button" disabled={busy} className={`${entryButton} mt-3 w-full`} onClick={onCancel}>{t("entry.inviteBack")}</button>
  </>;
}
