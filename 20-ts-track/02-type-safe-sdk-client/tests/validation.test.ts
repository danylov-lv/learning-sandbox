// Given test -- do not edit. MANDATORY anti-cheat check: the harness serves
// two routes that return HTTP 200 with a body that does not match the
// `Product` shape (`/products/malformed` has a stringified `price` and a
// missing `inStock`; `/products/wrongshape` is a completely different
// object). A client that does `return (await res.json()) as Product`
// happily "succeeds" against both -- these tests exist so that a
// cast-only implementation FAILS here even if every other test passes.
//
// Reached through the client's own generic `request(path, schema)` core
// (see `src/client.ts`), not a bespoke method, per the task's documented
// seam.

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { startMockServer, type MockServer } from "@sandbox19/harness";
import { ZodError } from "zod";
import { MarketplaceClient, ProductSchema, SdkValidationError } from "../src/index";

describe("validation of malformed responses", () => {
  let server: MockServer;
  let client: MarketplaceClient;

  beforeAll(async () => {
    server = await startMockServer();
    client = new MarketplaceClient({ baseUrl: server.baseUrl });
  });

  afterAll(async () => {
    await server.close();
  });

  it("rejects /products/malformed (stringified price, missing inStock) instead of returning it as-is", async () => {
    await expect(
      client.request("/products/malformed", ProductSchema),
      "a naive `as Product` cast would silently resolve here -- real schema validation must reject it",
    ).rejects.toThrow();

    try {
      await client.request("/products/malformed", ProductSchema);
      expect.fail("/products/malformed must fail schema validation");
    } catch (err) {
      expect(
        err instanceof SdkValidationError || err instanceof ZodError,
        "the rejection must be a validation error (SdkValidationError or the underlying ZodError), not some unrelated error",
      ).toBe(true);
    }
  });

  it("rejects /products/wrongshape ({ nope: true }) instead of returning it as-is", async () => {
    await expect(
      client.request("/products/wrongshape", ProductSchema),
      "a naive `as Product` cast would silently resolve here -- real schema validation must reject it",
    ).rejects.toThrow();

    try {
      await client.request("/products/wrongshape", ProductSchema);
      expect.fail("/products/wrongshape must fail schema validation");
    } catch (err) {
      expect(
        err instanceof SdkValidationError || err instanceof ZodError,
        "the rejection must be a validation error (SdkValidationError or the underlying ZodError), not some unrelated error",
      ).toBe(true);
    }
  });
});
