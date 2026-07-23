import { describe, expect, it } from "vitest";
import { assertNever } from "../src/05-event-by-tag";

describe("assertNever", () => {
  it("throws at runtime when the exhaustiveness guard is actually reached", () => {
    expect(
      () => assertNever("unreachable" as never),
      "assertNever must throw — it exists to make an unhandled variant a runtime failure, not a silent no-op",
    ).toThrow();
  });

  it("throws an Error with a non-empty message", () => {
    try {
      assertNever("unreachable" as never);
      expect.fail("assertNever must throw, not return");
    } catch (err) {
      expect(err, "assertNever must throw an Error instance").toBeInstanceOf(Error);
      expect(
        (err as Error).message.length > 0,
        "the thrown error should carry a readable message, not an empty string",
      ).toBe(true);
    }
  });
});
