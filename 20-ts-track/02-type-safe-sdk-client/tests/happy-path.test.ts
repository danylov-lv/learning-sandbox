// Given test -- do not edit. Verifies the basic single-resource read path:
// a well-formed response comes back fully typed, and a 404 comes back as
// the typed `ApiNotFoundError`, never a `ZodError` and never a bare `Error`.

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { startMockServer, type MockServer } from "@sandbox19/harness";
import { ZodError } from "zod";
import { ApiNotFoundError, MarketplaceClient } from "../src/index";

describe("getProduct", () => {
  let server: MockServer;
  let client: MarketplaceClient;

  beforeAll(async () => {
    server = await startMockServer();
    client = new MarketplaceClient({ baseUrl: server.baseUrl });
  });

  afterAll(async () => {
    await server.close();
  });

  it("returns the exact fixture product for id 1 (seed 0xc0ffee is deterministic)", async () => {
    const product = await client.getProduct(1);

    expect(product.id, "id must round-trip exactly").toBe(1);
    expect(product.sku, "sku is deterministic for this seed").toBe("SKU-00001");
    expect(product.name, "name is deterministic for this seed").toBe("Rustic Apparatus 1");
    expect(product.categoryId, "categoryId is deterministic for this seed").toBe(7);
    expect(product.sellerId, "sellerId is deterministic for this seed").toBe(9);
    expect(product.price, "price is deterministic for this seed").toBe(107.84);
    expect(product.inStock, "inStock is deterministic for this seed").toBe(true);
    expect(
      product.scrapedAt,
      "scrapedAt is deterministic for this seed",
    ).toBe("2024-01-01T01:00:00.000Z");
  });

  it("resolves fields with the correct runtime types, not just correct values", async () => {
    const product = await client.getProduct(2);

    expect(typeof product.id, "id must be a number").toBe("number");
    expect(typeof product.sku, "sku must be a string").toBe("string");
    expect(typeof product.name, "name must be a string").toBe("string");
    expect(typeof product.categoryId, "categoryId must be a number").toBe("number");
    expect(typeof product.sellerId, "sellerId must be a number").toBe("number");
    expect(typeof product.price, "price must be a number, not a numeric string").toBe(
      "number",
    );
    expect(typeof product.inStock, "inStock must be a boolean").toBe("boolean");
    expect(typeof product.scrapedAt, "scrapedAt must be a string").toBe("string");
  });

  it("rejects an unknown id with ApiNotFoundError, not a ZodError or a plain Error", async () => {
    await expect(
      client.getProduct(9999),
      "a 404 from the server must become a typed not-found error, not resolve",
    ).rejects.toThrow();

    try {
      await client.getProduct(9999);
      expect.fail("getProduct(9999) must reject -- the id does not exist in the fixture data");
    } catch (err) {
      expect(
        err instanceof ApiNotFoundError,
        "a 404 must surface as ApiNotFoundError so callers can instanceof-narrow on it",
      ).toBe(true);
      expect(
        err instanceof ZodError,
        "a 404's error envelope is well-formed JSON -- it must never be mistaken for a schema-validation failure",
      ).toBe(false);
      expect(
        (err as Error).constructor.name,
        "the rejection must not be a plain generic Error",
      ).not.toBe("Error");
    }
  });
});
