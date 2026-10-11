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
    expect(parseSession(valid)).toEqual(valid);
  });

  it.each([
    { ...valid, workspaces: [] },
    { ...valid, active_workspace: { ...workspace, id: "not-a-member" } },
    { ...valid, workspaces: [{ ...workspace, display_name: "" }] },
  ])("fails closed for inconsistent workspace data", (value) => {
    expect(() => parseSession(value)).toThrow();
  });
});
