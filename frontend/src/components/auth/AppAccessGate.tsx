import { type ReactNode, useEffect, useState } from "react";
import { Link, matchPath, useLocation } from "react-router-dom";
import { useTranslation } from "@/lib/i18n";
import { readAuthStatus, type AppAuthStatus } from "@/lib/appAuth";
import { AppReturnLink, EntryFrame, entryButton, entryControl } from "./EntryFrame";
import { SessionEntry } from "./SessionEntry";

export function AppAccessGate({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const location = useLocation();
  const [status, setStatus] = useState<AppAuthStatus | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setStatus(null); setFailed(false);
    void readAuthStatus(controller.signal).then((value) => {
      if (!controller.signal.aborted) setStatus(value);
    }).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [attempt]);

  if (!status) return (
    <EntryFrame>
      <p role={failed ? "alert" : "status"}>{t(failed ? "entry.error" : "entry.checking")}</p>
      {failed && <button type="button" className={`${entryButton} mt-5`} onClick={() => setAttempt(attempt + 1)}>{t("entry.retry")}</button>}
    </EntryFrame>
  );
  if (status.app_auth_required) return <EntryFrame><SessionEntry status={status} /></EntryFrame>;
  if (!matchPath("/login", location.pathname)) return (
    <>
      <nav aria-label={t("entry.title")} className="flex justify-end border-b border-border bg-surface-0 px-5">
        <Link className="inline-flex min-h-11 items-center text-sm text-text-secondary underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-focus" to="/login">{t("entry.title")}</Link>
      </nav>
      {children}
    </>
  );
  return (
    <EntryFrame>
      <h2 className="text-xl font-semibold tracking-tight">{t("entry.title")}</h2>
      <p className="mt-4 text-sm leading-relaxed text-text-secondary">{t("entry.disabled")}</p>
      <form className="mt-6 space-y-4" onSubmit={(event) => event.preventDefault()}>
        <label htmlFor="disabled-identifier" className="block text-sm">{t("entry.identifier")}<input id="disabled-identifier" disabled className={`${entryControl} mt-2 w-full`} /></label>
        <label htmlFor="disabled-password" className="block text-sm">{t("entry.password")}<input id="disabled-password" type="password" disabled className={`${entryControl} mt-2 w-full`} /></label>
        <button type="submit" disabled className={`${entryButton} w-full`}>{t("entry.signIn")}</button>
      </form>
      <AppReturnLink />
    </EntryFrame>
  );
}
