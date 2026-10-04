export interface AppAuthStatus {
  app_auth_required: boolean;
  finance_access_ready: false;
  session_transport: "https" | "https_or_loopback";
}

export function parseAuthStatus(value: unknown): AppAuthStatus {
  if (!value || typeof value !== "object") throw new Error("Invalid auth status");
  const status = value as Record<string, unknown>;
  // This release cannot open authenticated finance, even if a future backend
  // announces readiness. Activation needs a separately reviewed client rollout.
  if (typeof status.app_auth_required !== "boolean" || status.finance_access_ready !== false ||
      (status.session_transport !== "https" && status.session_transport !== "https_or_loopback")) {
    throw new Error("Invalid auth status");
  }
  return status as unknown as AppAuthStatus;
}

export function sessionTransportAllowed(status: AppAuthStatus, location: Pick<Location, "protocol" | "hostname">): boolean {
  if (location.protocol === "https:") return true;
  return status.session_transport === "https_or_loopback" && location.protocol === "http:" &&
    ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
}

export async function readAuthStatus(signal?: AbortSignal): Promise<AppAuthStatus> {
  const response = await fetch("/api/auth/status", { cache: "no-store", credentials: "same-origin", signal });
  if (!response.ok) throw new Error("Auth status unavailable");
  return parseAuthStatus(await response.json());
}
