import { describe, expect, it } from "vitest";
import { NAV_ITEMS, visibleNavItems } from "@/lib/navigation";

describe("primary navigation", () => {
  it("makes the help guide discoverable from the main navigation", () => {
    expect(NAV_ITEMS.some((item) => item.to === "/help" && item.labelKey === "nav.help")).toBe(true);
  });

  it("shows the administration page only to installation administrators", () => {
    expect(visibleNavItems(false).some((item) => item.to === "/admin")).toBe(false);
    expect(visibleNavItems(true).some((item) => item.to === "/admin")).toBe(true);
  });
});
