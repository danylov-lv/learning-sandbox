// A tiny deterministic HTTP mock server over Node's built-in `http` — no
// express, no extra deps. Serves module-12-shaped marketplace endpoints
// (sellers, categories, products, users, orders-domain) so the SDK task has a
// real, offline, reproducible backend to code against.
//
// It always binds 127.0.0.1:0 (ephemeral port) so parallel test runs never
// collide, and all data is generated from a fixed seed via an inlined
// mulberry32 PRNG. Some routes are DELIBERATELY malformed — they exist so a
// zod-validating SDK throws where a naive `as Product` cast would not.

import http from "node:http";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

export interface Product {
  id: number;
  sku: string;
  name: string;
  categoryId: number;
  sellerId: number;
  price: number;
  inStock: boolean;
  scrapedAt: string;
}

export interface User {
  id: number;
  email: string;
  displayName: string;
  role: "user" | "admin";
}

export interface ApiError {
  error: { code: string; message: string };
}

export interface MockServer {
  readonly baseUrl: string;
  readonly port: number;
  close(): Promise<void>;
}

// mulberry32: a compact, fast, well-distributed 32-bit PRNG. Deterministic
// given a seed — the whole dataset is a pure function of it.
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return function next(): number {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const CATEGORY_COUNT = 8;
const SELLER_COUNT = 12;
const PRODUCT_COUNT = 200;
const DEFAULT_LIMIT = 20;

const NOUNS = [
  "Widget",
  "Gadget",
  "Sprocket",
  "Gizmo",
  "Contraption",
  "Apparatus",
  "Doohickey",
  "Module",
] as const;
const ADJECTIVES = [
  "Rustic",
  "Sleek",
  "Rugged",
  "Compact",
  "Deluxe",
  "Vintage",
  "Modular",
  "Portable",
] as const;

function pick<T>(arr: readonly T[], rng: () => number): T {
  const idx = Math.floor(rng() * arr.length);
  // arr is non-empty by construction; clamp guards the rng()===1 edge.
  return arr[Math.min(idx, arr.length - 1)] as T;
}

function generateProducts(seed: number): Product[] {
  const rng = mulberry32(seed);
  const products: Product[] = [];
  const baseTime = Date.UTC(2024, 0, 1, 0, 0, 0);
  for (let i = 1; i <= PRODUCT_COUNT; i++) {
    const adjective = pick(ADJECTIVES, rng);
    const noun = pick(NOUNS, rng);
    const categoryId = 1 + Math.floor(rng() * CATEGORY_COUNT);
    const sellerId = 1 + Math.floor(rng() * SELLER_COUNT);
    const price = Math.round((1 + rng() * 998) * 100) / 100;
    const inStock = rng() > 0.25;
    const scrapedAt = new Date(baseTime + i * 3_600_000).toISOString();
    products.push({
      id: i,
      sku: `SKU-${String(i).padStart(5, "0")}`,
      name: `${adjective} ${noun} ${i}`,
      categoryId,
      sellerId,
      price,
      inStock,
      scrapedAt,
    });
  }
  return products;
}

// Fixture credentials — the one known-good login. Everything else is 401.
const FIXTURE_EMAIL = "buyer@example.com";
const FIXTURE_PASSWORD = "hunter2";
const FIXTURE_USER: User = {
  id: 1,
  email: FIXTURE_EMAIL,
  displayName: "Fixture Buyer",
  role: "user",
};

interface RequestContext {
  method: string;
  pathname: string;
  query: URLSearchParams;
  headers: IncomingMessage["headers"];
  body: unknown;
}

function readBody(req: IncomingMessage): Promise<unknown> {
  return new Promise((resolve) => {
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => chunks.push(c));
    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      if (raw.length === 0) {
        resolve(undefined);
        return;
      }
      try {
        resolve(JSON.parse(raw));
      } catch {
        resolve(undefined);
      }
    });
    req.on("error", () => resolve(undefined));
  });
}

function sendJson(res: ServerResponse, status: number, payload: unknown): void {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
  });
  res.end(body);
}

function errorBody(code: string, message: string): ApiError {
  return { error: { code, message } };
}

function encodeCursor(id: number): string {
  return Buffer.from(`id:${id}`, "utf8").toString("base64url");
}

function decodeCursor(cursor: string | null): number {
  if (cursor === null || cursor.length === 0) return 0;
  try {
    const decoded = Buffer.from(cursor, "base64url").toString("utf8");
    const match = /^id:(\d+)$/.exec(decoded);
    if (match && match[1] !== undefined) return Number.parseInt(match[1], 10);
  } catch {
    /* fall through to 0 */
  }
  return 0;
}

export async function startMockServer(opts?: {
  seed?: number;
}): Promise<MockServer> {
  const seed = opts?.seed ?? 0xc0ffee;
  const products = generateProducts(seed);
  const byId = new Map<number, Product>(products.map((p) => [p.id, p]));

  // Per-server auth state. Tokens are minted per login/refresh; refresh rotates
  // (the presented refresh token is invalidated and a fresh pair issued).
  let tokenCounter = 0;
  const accessTokens = new Map<string, number>(); // token -> userId
  const refreshTokens = new Map<string, number>(); // token -> userId

  function mintTokens(userId: number): {
    accessToken: string;
    refreshToken: string;
  } {
    tokenCounter += 1;
    const accessToken = `at_${seed.toString(16)}_${tokenCounter}`;
    const refreshToken = `rt_${seed.toString(16)}_${tokenCounter}`;
    accessTokens.set(accessToken, userId);
    refreshTokens.set(refreshToken, userId);
    return { accessToken, refreshToken };
  }

  function handle(ctx: RequestContext, res: ServerResponse): void {
    const { method, pathname, query } = ctx;

    // --- Deliberately-malformed routes (validation-test targets) ---
    if (method === "GET" && pathname === "/products/malformed") {
      const good = byId.get(1) as Product;
      // price as STRING, inStock MISSING — schema-invalid on purpose.
      const { inStock: _omit, ...rest } = good;
      sendJson(res, 200, { ...rest, price: String(good.price) });
      return;
    }
    if (method === "GET" && pathname === "/products/wrongshape") {
      sendJson(res, 200, { nope: true });
      return;
    }

    // --- /products collection (cursor pagination) ---
    if (method === "GET" && pathname === "/products") {
      const afterId = decodeCursor(query.get("cursor"));
      const rawLimit = Number.parseInt(query.get("limit") ?? "", 10);
      const limit =
        Number.isFinite(rawLimit) && rawLimit > 0
          ? Math.min(rawLimit, 100)
          : DEFAULT_LIMIT;
      const page = products.filter((p) => p.id > afterId).slice(0, limit);
      const last = page.length > 0 ? page[page.length - 1] : undefined;
      const more = last !== undefined && last.id < PRODUCT_COUNT;
      sendJson(res, 200, {
        items: page,
        nextCursor: last !== undefined && more ? encodeCursor(last.id) : null,
      });
      return;
    }

    // --- /products/:id ---
    if (method === "GET" && pathname.startsWith("/products/")) {
      const idPart = pathname.slice("/products/".length);
      const id = Number.parseInt(idPart, 10);
      const product = Number.isFinite(id) ? byId.get(id) : undefined;
      if (product === undefined) {
        sendJson(res, 404, errorBody("not_found", `no product ${idPart}`));
        return;
      }
      sendJson(res, 200, product);
      return;
    }

    // --- /categories/:id/summary ---
    if (method === "GET" && /^\/categories\/\d+\/summary$/.test(pathname)) {
      const categoryId = Number.parseInt(pathname.split("/")[2] ?? "", 10);
      const inCat = products.filter((p) => p.categoryId === categoryId);
      const inStockCount = inCat.filter((p) => p.inStock).length;
      const avgPrice =
        inCat.length > 0
          ? Math.round(
              (inCat.reduce((s, p) => s + p.price, 0) / inCat.length) * 100,
            ) / 100
          : 0;
      sendJson(res, 200, {
        categoryId,
        productCount: inCat.length,
        avgPrice,
        inStockCount,
      });
      return;
    }

    // --- /search?q= ---
    if (method === "GET" && pathname === "/search") {
      const q = (query.get("q") ?? "").toLowerCase();
      const items =
        q.length === 0
          ? []
          : products.filter((p) => p.name.toLowerCase().includes(q));
      sendJson(res, 200, { items });
      return;
    }

    // --- POST /auth/login ---
    if (method === "POST" && pathname === "/auth/login") {
      const body = (ctx.body ?? {}) as { email?: unknown; password?: unknown };
      if (
        body.email === FIXTURE_EMAIL &&
        body.password === FIXTURE_PASSWORD
      ) {
        sendJson(res, 200, mintTokens(FIXTURE_USER.id));
        return;
      }
      sendJson(res, 401, errorBody("invalid_credentials", "bad email/password"));
      return;
    }

    // --- POST /auth/refresh ---
    if (method === "POST" && pathname === "/auth/refresh") {
      const body = (ctx.body ?? {}) as { refreshToken?: unknown };
      const presented =
        typeof body.refreshToken === "string" ? body.refreshToken : "";
      const userId = refreshTokens.get(presented);
      if (userId === undefined) {
        sendJson(res, 401, errorBody("invalid_token", "unknown refresh token"));
        return;
      }
      refreshTokens.delete(presented); // rotate
      sendJson(res, 200, mintTokens(userId));
      return;
    }

    // --- GET /me ---
    if (method === "GET" && pathname === "/me") {
      const auth = ctx.headers["authorization"];
      const header = Array.isArray(auth) ? auth[0] : auth;
      const token = header?.startsWith("Bearer ")
        ? header.slice("Bearer ".length)
        : undefined;
      const userId =
        token !== undefined ? accessTokens.get(token) : undefined;
      if (userId === undefined) {
        sendJson(res, 401, errorBody("unauthorized", "missing/invalid token"));
        return;
      }
      sendJson(res, 200, FIXTURE_USER);
      return;
    }

    sendJson(res, 404, errorBody("not_found", `no route ${method} ${pathname}`));
  }

  const server = http.createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    void readBody(req).then((body) => {
      handle(
        {
          method: req.method ?? "GET",
          pathname: url.pathname,
          query: url.searchParams,
          headers: req.headers,
          body,
        },
        res,
      );
    });
  });

  await new Promise<void>((resolve) => {
    server.listen(0, "127.0.0.1", resolve);
  });

  const address = server.address() as AddressInfo;
  const port = address.port;
  const baseUrl = `http://127.0.0.1:${port}`;

  return {
    baseUrl,
    port,
    close(): Promise<void> {
      return new Promise((resolve, reject) => {
        server.close((err) => (err ? reject(err) : resolve()));
      });
    },
  };
}
