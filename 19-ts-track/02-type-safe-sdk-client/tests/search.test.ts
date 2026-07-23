// Given test -- do not edit. Verifies /search's two documented behaviors:
// case-insensitive substring matching, and an empty query returning an
// empty list rather than the whole catalog.

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { startMockServer, type MockServer } from "@sandbox19/harness";
import { MarketplaceClient } from "../src/index";

describe("search", () => {
  let server: MockServer;
  let client: MarketplaceClient;

  beforeAll(async () => {
    server = await startMockServer();
    client = new MarketplaceClient({ baseUrl: server.baseUrl });
  });

  afterAll(async () => {
    await server.close();
  });

  it("matches a substring of the product name case-insensitively", async () => {
    const lower = await client.search("widget");
    const upper = await client.search("WIDGET");
    const mixed = await client.search("WiDgEt");

    expect(lower.length, "seed 0xc0ffee has 23 products whose name contains 'widget'").toBe(
      23,
    );
    expect(upper.length, "an uppercase query must match the same set as lowercase").toBe(
      lower.length,
    );
    expect(mixed.length, "a mixed-case query must match the same set as lowercase").toBe(
      lower.length,
    );

    for (const product of lower) {
      expect(
        product.name.toLowerCase().includes("widget"),
        `"${product.name}" must actually contain "widget" (case-insensitively)`,
      ).toBe(true);
    }
  });

  it("returns an empty list for an empty query, not the whole catalog", async () => {
    const results = await client.search("");

    expect(
      results,
      "an empty query must come back as an empty list, mirroring the server's documented behavior",
    ).toEqual([]);
  });
});
