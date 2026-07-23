// @t3/web — the typed client.
//
// Notice this package's package.json has no @t3/api dependency at all —
// on purpose. ProductsPort below is expressed entirely in @t3/contracts
// types, so whatever object @t3/api's createApiHandlers() returns
// satisfies it structurally, with no compile-time coupling between the
// two packages. @t3/e2e is the only place that imports both and wires
// them together. This is the same shape a real frontend/BFF boundary
// takes: the web layer depends on a contract, not on the service that
// happens to implement it today.

import type { ListProductsParams, Product, ProductPage } from "@t3/contracts";

/**
 * The subset of @t3/api's ApiHandlers that @t3/web depends on, expressed
 * purely in @t3/contracts types.
 */
export interface ProductsPort {
  getProduct(id: number): Promise<Product>;
  listProducts(params: ListProductsParams): Promise<ProductPage>;
}

/**
 * @t3/web's typed client surface, handed to application code.
 */
export interface WebClient {
  getProduct(id: number): Promise<Product>;
  listProducts(params: ListProductsParams): Promise<ProductPage>;
}

/**
 * Wraps `port` so every value it returns is RE-VALIDATED against
 * @t3/contracts' schemas before being handed back to the caller. This is
 * the anti-cast check: `port`'s TypeScript return type already promises a
 * Product/ProductPage, but types are erased at runtime — if `port` is
 * lying (a bug, a misbehaving upstream, or a malformed value injected by a
 * test), a naive `return await port.getProduct(id)` would silently pass
 * the lie through. Parse with `ProductSchema.parse(...)` /
 * `ProductPageSchema.parse(...)` instead, so a shape mismatch throws a
 * ZodError right here, at the boundary, instead of surfacing as a
 * confusing bug somewhere downstream. CP3 injects exactly this kind of
 * malformed value through a fake port to check it.
 */
export function createWebClient(port: ProductsPort): WebClient {
  return {
    async getProduct(id) {
      throw new Error(`not implemented: createWebClient(port).getProduct(${id})`);
    },
    async listProducts(params) {
      throw new Error(
        `not implemented: createWebClient(port).listProducts(${JSON.stringify(params)})`,
      );
    },
  };
}
