// @t3/contracts — the Product family.
//
// This is the single source of truth for the marketplace "Product" shape
// and the request/response DTOs built on top of it. @t3/api, @t3/worker,
// and @t3/web all import these types and schemas directly — they must
// never redeclare their own copies. When a field here changes, every
// consumer either updates in lockstep or fails its own typecheck/test;
// that coupling is the whole point of this package.
//
// Every schema below is a z.unknown() placeholder. Replace each with a
// real zod schema for the shape documented above it — the doc comment IS
// the spec, pinned exactly, the same way a wire format or byte layout
// would be pinned in any other task in this repo.

import { z } from "zod";

/**
 * One marketplace product. Mirrors `@sandbox19/harness`'s mock-server
 * `Product` shape exactly (same field names, same types) — this is what
 * every `/products*` route response must validate against:
 *
 *   {
 *     id: number;
 *     sku: string;
 *     name: string;
 *     categoryId: number;
 *     sellerId: number;
 *     price: number;
 *     inStock: boolean;
 *     scrapedAt: string;
 *   }
 */
export const ProductSchema = z.unknown();
export type Product = z.infer<typeof ProductSchema>;

/**
 * One page of a cursor-paginated product listing, as returned by
 * `GET /products`:
 *
 *   { items: Product[]; nextCursor: string | null }
 */
export const ProductPageSchema = z.unknown();
export type ProductPage = z.infer<typeof ProductPageSchema>;

/**
 * Query parameters accepted by the product-listing handler. Both optional
 * — `cursor` is an opaque token (only ever round-tripped, never built by
 * hand), `limit` is a positive page size:
 *
 *   { cursor?: string; limit?: number }
 */
export const ListProductsParamsSchema = z.unknown();
export type ListProductsParams = z.infer<typeof ListProductsParamsSchema>;

/**
 * Aggregate stats for one category, as returned by
 * `GET /categories/:id/summary`:
 *
 *   { categoryId: number; productCount: number; avgPrice: number; inStockCount: number }
 */
export const CategorySummarySchema = z.unknown();
export type CategorySummary = z.infer<typeof CategorySummarySchema>;

/**
 * Result of a name search, as returned by `GET /search?q=`:
 *
 *   { items: Product[] }
 */
export const SearchResultSchema = z.unknown();
export type SearchResult = z.infer<typeof SearchResultSchema>;
