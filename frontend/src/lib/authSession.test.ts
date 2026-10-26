import { describe, expect, it } from "vitest";
import { parseSession } from "./authSession";

const workspace = { id: "workspace-one", display_name: "Personal", kind: "personal", role: "owner" };
const valid = {
  user: { id: "user-one", identifier: "owner@example.com", display_name: "Owner" },
  csrf_token: "csrf-token",
  workspaces: [workspace],
  active_workspace: workspace,
};

describe("parseSession", () => {
  it("keeps the verified workspace membership in memory", () => {
    const active = { ...workspace, status: "active" };
    expect(parseSession(valid)).toEqual({
      ...valid,
      user: { ...valid.user, is_admin: false },
      workspaces: [active],
      active_workspace: active,
    });
  });

  it("reports the admin flag and blocked workspaces", () => {
    const blocked = { ...workspace, status: "blocked" };
    const parsed = parseSession({ ...valid, user: { ...valid.user, is_admin: true }, workspaces: [blocked], active_workspace: blocked });
    expect(parsed.user.is_admin).toBe(true);
    expect(parsed.active_workspace.status).toBe("blocked");
  });

  it.each([
    { ...valid, workspaces: [] },
    { ...valid, active_workspace: { ...workspace, id: "not-a-member" } },
    { ...valid, workspaces: [{ ...workspace, display_name: "" }] },
    { ...valid, workspaces: [{ ...workspace, status: "frozen" }], active_workspace: { ...workspace, status: "frozen" } },
  ])("fails closed for inconsistent workspace data", (value) => {
    expect(() => parseSession(value)).toThrow();
  });
});
