import { expect, it } from "vitest";
import { parseAuthStatus, sessionTransportAllowed } from "./appAuth";

const dev = { app_auth_required: true, finance_access_ready: false, session_transport: "https_or_loopback", initial_owner_bootstrap_required: false, initial_owner_bootstrap_available: false } as const;
it.each([
  ["https:", "aurum.example", "https", true],
  ["http:", "localhost", "https", false],
  ["http:", "localhost", "https_or_loopback", true],
  ["http:", "127.0.0.1", "https_or_loopback", true],
  ["http:", "[::1]", "https_or_loopback", true],
  ["http:", "192.168.1.10", "https_or_loopback", false],
  ["http:", "localhost.evil.example", "https_or_loopback", false],
  ["file:", "localhost", "https_or_loopback", false],
] as const)("session transport %s %s with %s is %s", (protocol, hostname, transport, expected) => {
  expect(sessionTransportAllowed({ ...dev, session_transport: transport }, { protocol, hostname })).toBe(expected);
});
it.each([
  { ...dev, session_transport: "insecure" },
  { app_auth_required: false, finance_access_ready: false },
  { ...dev, finance_access_ready: true },
  { ...dev, finance_access_ready: undefined },
  { ...dev, app_auth_required: 0 },
])("incomplete or permissive status is rejected: %j", (status) => {
  expect(() => parseAuthStatus(status)).toThrow("Invalid auth status");
});
