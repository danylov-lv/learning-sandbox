// @t3/api — the request-handler layer.
//
// This stands in for a backend service that talks to the upstream
// marketplace HTTP API (in this task's tests, the harness's
// `startMockServer()`) and hands back contract-typed data. Every method's
// parameter and return type below is expressed entirely in @t3/contracts
// types, imported — never redeclared. @t3/e2e's CP1 checks that literally,
// at the type level: redeclaring a look-alike shape here instead of
// importing it from @t3/contracts defeats the point, and silently stops
// tracking future contract changes.

import type {
  ApiError,
  CategorySummary,
  ListProductsParams,
  Product,
  ProductPage,
  SearchResult,
} from "@t3/contracts";

/**
 * Thrown by every ApiHandlers method when the upstream marketplace
 * responds with a non-2xx status. Carries the parsed, contract-typed
 * ApiError body — never an untyped/opaque throw.
 */
export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    public readonly apiError: ApiError,
  ) {
    super(`api request failed with status ${status}`);
    this.name = "ApiRequestError";
  }
}

/**
 * The api service's request-handler surface.
 */
export interface ApiHandlers {
  listProducts(params: ListProductsParams): Promise<ProductPage>;
  getProduct(id: number): Promise<Product>;
  getCategorySummary(categoryId: number): Promise<CategorySummary>;
  searchProducts(q: string): Promise<SearchResult>;
}

/**
 * Builds an ApiHandlers backed by an upstream marketplace HTTP API at
 * `baseUrl`. Every method must:
 *
 *   1. Issue the matching HTTP request (`GET /products`, `GET /products/:id`,
 *      `GET /categories/:id/summary`, `GET /search?q=`).
 *   2. On a non-2xx response, parse the body against ApiErrorSchema and
 *      throw ApiRequestError — never let a malformed error body silently
 *      become `undefined` or an untyped throw.
 *   3. On a 2xx response, parse the body against the matching contract
 *      schema (e.g. `ProductSchema.parse(json)`) before returning it — a
 *      bare `json as Product` cast defeats the entire exercise; CP1
 *      exercises this against the harness's deliberately-malformed routes
 *      by hitting them through this handler.
 */
export function createApiHandlers(baseUrl: string): ApiHandlers {
  return {
    async listProducts(params) {
      throw new Error(
        `not implemented: createApiHandlers(${baseUrl}).listProducts(${JSON.stringify(params)})`,
      );
    },
    async getProduct(id) {
      throw new Error(`not implemented: createApiHandlers(${baseUrl}).getProduct(${id})`);
    },
    async getCategorySummary(categoryId) {
      throw new Error(
        `not implemented: createApiHandlers(${baseUrl}).getCategorySummary(${categoryId})`,
      );
    },
    async searchProducts(q) {
      throw new Error(`not implemented: createApiHandlers(${baseUrl}).searchProducts(${q})`);
    },
  };
}
