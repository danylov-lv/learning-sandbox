// Given test -- do not edit. Verifies the auth flow: login happy/unhappy
// paths, me() while logged in, refresh rotation (the old refresh token is
// invalidated), and me()'s automatic single-retry refresh when the stored
// access token is invalid but the stored refresh token is still good.

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { startMockServer, type MockServer } from "@sandbox19/harness";
import { ApiAuthError, AuthTokensSchema, MarketplaceClient } from "../src/index";

const GOOD_EMAIL = "buyer@example.com";
const GOOD_PASSWORD = "hunter2";

describe("auth", () => {
  let server: MockServer;

  beforeAll(async () => {
    server = await startMockServer();
  });

  afterAll(async () => {
    await server.close();
  });

  it("login with correct credentials returns and stores a token pair", async () => {
    const client = new MarketplaceClient({ baseUrl: server.baseUrl });

    const tokens = await client.login(GOOD_EMAIL, GOOD_PASSWORD);

    expect(typeof tokens.accessToken, "accessToken must be a string").toBe("string");
    expect(typeof tokens.refreshToken, "refreshToken must be a string").toBe("string");
    expect(
      client.getTokens(),
      "a successful login must store the tokens on the client, not just return them",
    ).toEqual(tokens);
  });

  it("login with bad credentials rejects with ApiAuthError, not a bare Error", async () => {
    const client = new MarketplaceClient({ baseUrl: server.baseUrl });

    try {
      await client.login("nobody@example.com", "wrong-password");
      expect.fail("login with bad credentials must reject");
    } catch (err) {
      expect(
        err instanceof ApiAuthError,
        "bad credentials (401) must surface as ApiAuthError",
      ).toBe(true);
    }
  });

  it("me() returns the fixture user once logged in", async () => {
    const client = new MarketplaceClient({ baseUrl: server.baseUrl });
    await client.login(GOOD_EMAIL, GOOD_PASSWORD);

    const user = await client.me();

    expect(user.email, "me() must return the fixture buyer's email").toBe(GOOD_EMAIL);
    expect(user.displayName, "me() must return the fixture buyer's display name").toBe(
      "Fixture Buyer",
    );
    expect(user.role, "me() must return the fixture buyer's role").toBe("user");
  });

  it("refresh() rotates the token pair, invalidating the presented refresh token", async () => {
    const client = new MarketplaceClient({ baseUrl: server.baseUrl });
    const original = await client.login(GOOD_EMAIL, GOOD_PASSWORD);

    const rotated = await client.refresh();

    expect(
      rotated.refreshToken,
      "the server mints a brand-new refresh token on every rotation",
    ).not.toBe(original.refreshToken);
    expect(
      rotated.accessToken,
      "the server mints a brand-new access token on every rotation",
    ).not.toBe(original.accessToken);
    expect(
      client.getTokens(),
      "refresh() must store the rotated pair on the client",
    ).toEqual(rotated);

    // Reusing the original (now-rotated-away) refresh token must be rejected --
    // exercised via the SDK's own generic `request` core against the same
    // endpoint `refresh()` uses internally.
    await expect(
      client.request("/auth/refresh", AuthTokensSchema, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ refreshToken: original.refreshToken }),
      }),
      "a refresh token that was already rotated away must be rejected by the server",
    ).rejects.toThrow();
  });

  it("me() auto-refreshes exactly once when the access token is invalid but the refresh token is valid", async () => {
    const seeder = new MarketplaceClient({ baseUrl: server.baseUrl });
    const goodTokens = await seeder.login(GOOD_EMAIL, GOOD_PASSWORD);

    const client = new MarketplaceClient({
      baseUrl: server.baseUrl,
      tokens: { accessToken: "definitely-not-a-real-token", refreshToken: goodTokens.refreshToken },
    });

    const user = await client.me();

    expect(
      user.email,
      "me() must transparently refresh and still return the fixture user",
    ).toBe(GOOD_EMAIL);

    const newTokens = client.getTokens();
    expect(
      newTokens?.accessToken,
      "after the auto-refresh, the client must be holding a real (rotated) access token",
    ).not.toBe("definitely-not-a-real-token");
    expect(
      newTokens?.refreshToken,
      "the refresh triggered by me() must also rotate the refresh token",
    ).not.toBe(goodTokens.refreshToken);
  });

  it("me() rejects with ApiAuthError when both the access and refresh tokens are invalid", async () => {
    const client = new MarketplaceClient({
      baseUrl: server.baseUrl,
      tokens: { accessToken: "garbage-access", refreshToken: "garbage-refresh" },
    });

    try {
      await client.me();
      expect.fail("me() must reject when neither token is valid");
    } catch (err) {
      expect(
        err instanceof ApiAuthError,
        "an unrecoverable 401 (refresh also failed) must surface as ApiAuthError",
      ).toBe(true);
    }
  });
});
