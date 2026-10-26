import { type ReactNode, useCallback, useEffect, useState } from "react";
import { Link, matchPath, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "@/lib/i18n";
import { readAuthStatus, type AppAuthStatus } from "@/lib/appAuth";
import { AppReturnLink, EntryFrame, entryButton, entryControl } from "./EntryFrame";
import { InitialOwnerBootstrap } from "./InitialOwnerBootstrap";
import { InvitationSignup, takeInvitationFromHash } from "./InvitationSignup";
import { PasswordResetConfirm, PasswordResetRequest, takeResetTokenFromLocation } from "./PasswordReset";
import { SessionEntry } from "./SessionEntry";
import { WorkspaceProvider } from "@/contexts/WorkspaceContext";
import { setApiSessionContext } from "@/api/client";
import type { IdentitySession } from "@/lib/authSession";

export function AppAccessGate({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const [status, setStatus] = useState<AppAuthStatus | null>(null);
  const [session, setSession] = useState<IdentitySession | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  // An invitation link (/login#invite=CODE) opens account creation directly.
  const [invitation, setInvitation] = useState<{ token: string | null } | null>(() => {
    const token = takeInvitationFromHash();
    return token ? { token } : null;
  });
  // "Forgot password?" form, or the page opened from an e-mailed reset link.
  const [recovery, setRecovery] = useState<{ mode: "request" } | { mode: "confirm"; token: string } | null>(() => {
    const token = takeResetTokenFromLocation();
    return token ? { mode: "confirm", token } : null;
  });
  const finishRecovery = useCallback(() => {
    // A completed reset revokes every session, so identity is re-read from scratch.
    setRecovery(null); setStatus(null);
    navigate("/login", { replace: true });
    setAttempt((value) => value + 1);
  }, [navigate]);
  const grantFinanceAccess = useCallback((verified: IdentitySession) => {
    setApiSessionContext({ csrfToken: verified.csrf_token, workspaceId: verified.active_workspace.id });
    setSession(verified);
  }, []);
  const endSession = useCallback(() => setSession(null), []);
  useEffect(() => {
    const controller = new AbortController();
    setStatus(null); setSession(null); setApiSessionContext(null); setFailed(false);
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
  if (status.initial_owner_bootstrap_required) return (
    <EntryFrame><InitialOwnerBootstrap status={status} onComplete={() => setAttempt((value) => value + 1)} /></EntryFrame>
  );
  if (status.app_auth_required) {
    // A reset link wins even over an open session: it may be another account's.
    if (recovery?.mode === "confirm") return (
      <EntryFrame><PasswordResetConfirm status={status} token={recovery.token} onDone={finishRecovery} /></EntryFrame>
    );
    if (status.finance_access_ready && session) return <WorkspaceProvider session={session} onSessionEnded={endSession}>{children}</WorkspaceProvider>;
    if (invitation && !session) return (
      <EntryFrame>
        <InvitationSignup
          status={status}
          initialToken={invitation.token}
          onComplete={() => { setStatus(null); setInvitation(null); setAttempt((value) => value + 1); }}
          onCancel={() => setInvitation(null)}
        />
      </EntryFrame>
    );
    if (recovery?.mode === "request" && !session) return (
      <EntryFrame><PasswordResetRequest status={status} onBack={() => setRecovery(null)} /></EntryFrame>
    );
    return (
      <EntryFrame>
        <SessionEntry
          status={status}
          onFinanceAccessGranted={grantFinanceAccess}
          onInvitation={() => setInvitation({ token: null })}
          onForgotPassword={status.password_reset_available ? () => setRecovery({ mode: "request" }) : undefined}
        />
      </EntryFrame>
    );
  }
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
