import { describe, expect, it } from "vitest";
import { toUserId, toProductId } from "../src/12-brand";

describe("branded id constructors", () => {
  it("toUserId preserves the underlying runtime number unchanged", () => {
    expect(
      toUserId(42) as unknown as number,
      "branding is a compile-time-only cast — the runtime value must be untouched",
    ).toBe(42);
  });

  it("toProductId preserves the underlying runtime number unchanged", () => {
    expect(
      toProductId(7) as unknown as number,
      "branding is a compile-time-only cast — the runtime value must be untouched",
    ).toBe(7);
  });

  it("two different raw numbers stay distinguishable after branding", () => {
    const a = toUserId(1) as unknown as number;
    const b = toUserId(2) as unknown as number;
    expect(a === b, "branding must not collapse distinct ids to the same runtime value").toBe(false);
  });
});
