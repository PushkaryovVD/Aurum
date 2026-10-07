import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "@/lib/i18n";
import { sessionTransportAllowed, type AppAuthStatus } from "@/lib/appAuth";
import { entryButton, entryControl } from "./EntryFrame";

/** One-time operator-code ceremony; it is not public registration. */
export function InitialOwnerBootstrap({ status, onComplete }: {
  status: AppAuthStatus;
  onComplete: () => void;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const allowed = sessionTransportAllowed(status, window.location);
  const enabled = allowed && status.initial_owner_bootstrap_available && !busy;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!enabled) return;
    const values = new FormData(event.currentTarget);
    const bootstrap_code = String(values.get("bootstrap_code") ?? "");
    const identifier = String(values.get("identifier") ?? "");
    const display_name = String(values.get("display_name") ?? "");
    const password = String(values.get("password") ?? "");
    if (!bootstrap_code || !identifier || !display_name || !password) return;
    setBusy(true); setMessage(null);
    try {
      const response = await fetch("/api/auth/bootstrap/initial-owner", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bootstrap_code, identifier, display_name, password }),
      });
      formRef.current?.reset();
      if (response.ok) {
        onComplete();
        return;
      }
      setMessage(t("entry.bootstrapError"));
    } catch {
      setMessage(t("entry.bootstrapNetwork"));
    } finally { setBusy(false); }
  }

  return <>
    <h2 className="text-xl font-semibold tracking-tight">{t("entry.bootstrapTitle")}</h2>
    <p className="mt-4 text-sm leading-relaxed text-text-secondary">{t("entry.bootstrapIntro")}</p>
    {!allowed && <p className="mt-5 text-sm text-warning" role="alert">{t("entry.transport")}</p>}
    {!status.initial_owner_bootstrap_available && <p className="mt-5 text-sm text-warning" role="alert">{t("entry.bootstrapExpired")}</p>}
    {message && <p className="mt-5 text-sm" role="status">{message}</p>}
    <form ref={formRef} className="mt-6 space-y-4" onSubmit={(event) => void submit(event)} aria-busy={busy}>
      <label className="block text-sm" htmlFor="initial-owner-code">{t("entry.bootstrapCode")}<input id="initial-owner-code" name="bootstrap_code" type="password" autoComplete="one-time-code" required disabled={!enabled} className={`${entryControl} mt-2 w-full`} /></label>
      <label className="block text-sm" htmlFor="initial-owner-name">{t("entry.bootstrapName")}<input id="initial-owner-name" name="display_name" autoComplete="name" required maxLength={100} disabled={!enabled} className={`${entryControl} mt-2 w-full`} /></label>
      <label className="block text-sm" htmlFor="initial-owner-identifier">{t("entry.identifier")}<input id="initial-owner-identifier" name="identifier" autoComplete="username" required maxLength={320} disabled={!enabled} className={`${entryControl} mt-2 w-full`} /></label>
      <label className="block text-sm" htmlFor="initial-owner-password">{t("entry.password")}<input id="initial-owner-password" name="password" type="password" autoComplete="new-password" required minLength={12} maxLength={1024} disabled={!enabled} className={`${entryControl} mt-2 w-full`} /></label>
      <button type="submit" disabled={!enabled} className={`${entryButton} w-full`}>{busy ? t("entry.bootstrapSubmitting") : t("entry.bootstrapSubmit")}</button>
    </form>
  </>;
}
