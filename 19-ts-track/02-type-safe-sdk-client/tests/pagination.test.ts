// Given test -- do not edit. Verifies cursor pagination: page size is
// respected, `nextCursor` chains correctly, and `iterateProducts` walks the
// whole 200-product fixture exactly once each, in ascending id order.

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { startMockServer, type MockServer } from "@sandbox19/harness";
import { MarketplaceClient } from "../src/index";

describe("listProducts / iterateProducts", () => {
  let server: MockServer;
  let client: MarketplaceClient;

  beforeAll(async () => {
    server = await startMockServer();
    client = new MarketplaceClient({ baseUrl: server.baseUrl });
  });

  afterAll(async () => {
    await server.close();
  });

  it("respects the requested page size and returns a non-null cursor mid-stream", async () => {
    const page = await client.listProducts({ limit: 5 });

    expect(page.items.length, "a limit of 5 must return exactly 5 items").toBe(5);
    expect(
      page.items.map((p) => p.id),
      "the first page must be the first 5 ids in ascending order",
    ).toEqual([1, 2, 3, 4, 5]);
    expect(
      page.nextCursor,
      "there are 200 products, so a 5-item first page must have a next page",
    ).not.toBeNull();
  });

  it("chains cursors to the next page without skipping or repeating ids", async () => {
    const page1 = await client.listProducts({ limit: 5 });
    const cursor = page1.nextCursor;
    expect(cursor, "page 1's nextCursor must be usable as page 2's cursor").not.toBeNull();

    const page2 = await client.listProducts({ limit: 5, cursor });

    expect(
      page2.items.map((p) => p.id),
      "page 2 must continue immediately after page 1's last id",
    ).toEqual([6, 7, 8, 9, 10]);
  });

  it("caps an oversized limit at 100 server-side", async () => {
    const page = await client.listProducts({ limit: 200 });

    expect(page.items.length, "the server caps limit at 100 regardless of what was asked").toBe(
      100,
    );
    expect(
      page.nextCursor,
      "100 of 200 products fit on this page, so there must be a next page",
    ).not.toBeNull();
  });

  it("returns a null cursor on the last page", async () => {
    const page1 = await client.listProducts({ limit: 100 });
    const page2 = await client.listProducts({ limit: 100, cursor: page1.nextCursor });

    expect(page2.items.length, "the second page of 100 covers the remaining half").toBe(100);
    expect(page2.nextCursor, "the last page's nextCursor must be null").toBeNull();
  });

  it("iterateProducts yields exactly 200 unique ids in ascending order", async () => {
    const ids: number[] = [];
    for await (const product of client.iterateProducts({ limit: 37 })) {
      ids.push(product.id);
    }

    expect(ids.length, "the fixture has exactly 200 products").toBe(200);
    expect(
      new Set(ids).size,
      "iterateProducts must not yield the same product twice across pages",
    ).toBe(200);

    const sorted = [...ids].sort((a, b) => a - b);
    expect(
      ids,
      "iterateProducts must yield in ascending id order, matching the server's keyset order",
    ).toEqual(sorted);
    expect(ids[0], "the first yielded id must be 1").toBe(1);
    expect(ids[ids.length - 1], "the last yielded id must be 200").toBe(200);
  });
});
