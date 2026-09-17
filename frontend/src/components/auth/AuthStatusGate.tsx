import { type ReactNode, useEffect, useState } from "react";

import { NoAuthModal } from "@/components/auth/NoAuthModal";

interface AuthStatus {
  enabled: boolean;
}

/**
 * Authentication itself is entirely owned by nginx and the browser. This
 * component only preserves Aurum's warning for deliberately unprotected
 * installations; it never handles credentials or blocks the application.
 */
export function AuthStatusGate({ children }: { children: ReactNode }) {
  const [authEnabled, setAuthEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/auth-status.json", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) return null;
        return (await response.json()) as AuthStatus;
      })
      .then((status) => setAuthEnabled(status?.enabled ?? null))
      .catch(() => setAuthEnabled(null));
    return () => controller.abort();
  }, []);

  return (
    <>
      {authEnabled === false && <NoAuthModal />}
      {children}
    </>
  );
}
