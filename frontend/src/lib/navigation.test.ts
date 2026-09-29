import { describe, expect, it } from "vitest";
import { NAV_ITEMS } from "@/lib/navigation";

describe("primary navigation", () => {
  it("makes the help guide discoverable from the main navigation", () => {
    expect(NAV_ITEMS.some((item) => item.to === "/help" && item.labelKey === "nav.help")).toBe(true);
  });
});
