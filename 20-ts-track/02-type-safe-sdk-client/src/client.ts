/**
 * A validated client for the harness marketplace API
 * (`@sandbox19/harness`'s `startMockServer()`). Every response is parsed
 * through a zod schema before it reaches a caller: a well-formed 2xx
 * response becomes a typed value, a schema-invalid body throws
 * `SdkValidationError`, and a non-2xx response throws one of the typed
 * errors in `./errors` -- a caller of this client should never need to
 * write `as Product` (or any other `as`) to make a response usable, and
 * should never receive a garbage-shaped value typed as if it were valid.
 */

import type { ZodType } from "zod";
import {
  ApiErrorSchema,
  AuthTokensSchema,
  CategorySummarySchema,
  ProductSchema,
  ProductsPageSchema,
  SearchResultSchema,
  UserSchema,
  type AuthTokens,
  type CategorySummary,
  type Product,
  type ProductsPage,
  type User,
} from "./schemas";
import {
  ApiAuthError,
  ApiNotFoundError,
  ApiRequestError,
  SdkValidationError,
} from "./errors";

export interface MarketplaceClientOptions {
  /** e.g. `mockServer.baseUrl`. No trailing slash is assumed either way. */
  baseUrl: string;
  /**
   * Seed the client with an existing token pair, skipping `login()`. Tests
   * use this (together with `setTokens`) to construct a client that is
   * already "logged in", or to inject a deliberately-invalid access token
   * alongside a valid refresh token to exercise `me()`'s refresh path.
   */
  tokens?: AuthTokens;
}

export class MarketplaceClient {
  constructor(options: MarketplaceClientOptions) {
    throw new Error("not implemented");
  }

  /** The currently stored token pair, or `undefined` before login/seeding. */
  getTokens(): AuthTokens | undefined {
    throw new Error("not implemented");
  }

  /** Replace the stored token pair. Pass `undefined` to log the client out. */
  setTokens(tokens: AuthTokens | undefined): void {
    throw new Error("not implemented");
  }

  /**
   * The generic validated request core every typed method below is built
   * on. `path` is resolved against `baseUrl` (e.g. `"/products/7"`). On a
   * 2xx response, the JSON body is validated with `schema`; a mismatch must
   * surface as `SdkValidationError` (wrapping the `ZodError`), never as a
   * silently-cast value and never as a bare unwrapped `ZodError`. On a
   * non-2xx response: 404 -> `ApiNotFoundError`, 401 -> `ApiAuthError`,
   * anything else -> `ApiRequestError`.
   *
   * This method is deliberately public and generic: it is the seam used to
   * validate arbitrary endpoints (including the deliberately-malformed
   * `/products/malformed` and `/products/wrongshape` routes) without a
   * dedicated typed method for each one.
   */
  async request<T>(
    path: string,
    schema: ZodType<T>,
    init?: RequestInit,
  ): Promise<T> {
    throw new Error("not implemented");
  }

  /** GET /products/:id. Rejects with `ApiNotFoundError` for an unknown id -- never a `ZodError`. */
  async getProduct(id: number): Promise<Product> {
    throw new Error("not implemented");
  }

  /**
   * GET /products?cursor=&limit=. `limit` is optional (the server defaults
   * to 20, capped at 100); `cursor` is the opaque `nextCursor` from a
   * previous page, or omitted/`null` for the first page.
   */
  async listProducts(opts?: {
    limit?: number;
    cursor?: string | null;
  }): Promise<ProductsPage> {
    throw new Error("not implemented");
  }

  /**
   * Walks every page of `/products` in ascending id order, yielding one
   * `Product` at a time by following `nextCursor` until it is `null`. Must
   * terminate, and must not yield the same id twice.
   */
  async *iterateProducts(opts?: { limit?: number }): AsyncGenerator<Product, void, void> {
    throw new Error("not implemented");
  }

  /** GET /categories/:id/summary. */
  async getCategorySummary(categoryId: number): Promise<CategorySummary> {
    throw new Error("not implemented");
  }

  /** GET /search?q=. An empty `q` returns `[]` (mirroring the server). */
  async search(q: string): Promise<Product[]> {
    throw new Error("not implemented");
  }

  /**
   * POST /auth/login. On success, stores the returned tokens on this
   * client (so a subsequent `me()` works without a separate `setTokens`
   * call) and returns them. Rejects with `ApiAuthError` on bad credentials.
   */
  async login(email: string, password: string): Promise<AuthTokens> {
    throw new Error("not implemented");
  }

  /**
   * POST /auth/refresh, using the stored refresh token. The server rotates
   * on every call -- the presented refresh token is invalidated and a new
   * pair is issued. Stores the new pair and returns it. Rejects with
   * `ApiAuthError` if there is no stored refresh token, or the server
   * rejects the one presented (e.g. it was already rotated away).
   */
  async refresh(): Promise<AuthTokens> {
    throw new Error("not implemented");
  }

  /**
   * GET /me using the stored access token. On a 401, attempts exactly one
   * `refresh()` and retries `/me` once with the newly-rotated access
   * token. A second 401 (or no stored refresh token to attempt) propagates
   * as `ApiAuthError` -- there is no retry loop.
   */
  async me(): Promise<User> {
    throw new Error("not implemented");
  }
}
