import { describe, expect, it } from "vitest";
import { queryDisplayState } from "./queryDisplayState";

describe("queryDisplayState", () => {
  it("keeps initial loading distinct from an empty successful result", () => {
    expect(queryDisplayState(false, true, false)).toBe("loading");
    expect(queryDisplayState(true, false, false)).toBe("ready");
  });

  it("does not turn an unavailable response into confirmed empty data", () => {
    expect(queryDisplayState(false, false, true)).toBe("unavailable");
  });

  it("retains cached data only with an explicit stale state", () => {
    expect(queryDisplayState(true, false, true)).toBe("stale");
  });
});

