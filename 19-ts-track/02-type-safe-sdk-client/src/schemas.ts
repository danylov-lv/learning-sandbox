/**
 * Zod schemas for every shape the marketplace API returns, plus the types
 * inferred from them. This is the core of the task: every exported type
 * below must come from `z.infer<typeof SomeSchema>` -- never a hand-written
 * `interface`/`type` that merely happens to look right. If a type here was
 * not produced by `z.infer`, the schema isn't doing its job.
 *
 * Every schema constant currently reads `z.custom<...>(() => true)`. That
 * stub pins the *compile-time* type (so the rest of the package, and the
 * given tests, typecheck against the correct shape before you've written a
 * line of real validation) but validates NOTHING at runtime -- `.parse()`
 * on a `z.custom(() => true)` schema accepts any value whatsoever. Replace
 * each stub with a real schema (`z.object`, `z.string`, `z.number`,
 * `.nullable()`, etc.) built from the field-by-field shape documented on
 * each schema below. The type alias exported next to it must keep resolving
 * via `z.infer` -- do not also hand-write the interface once the schema is
 * real; delete the stub's type parameter along with `z.custom`.
 */

import { z } from "zod";
import type {
  ApiError as HarnessApiError,
  Product as HarnessProduct,
  User as HarnessUser,
} from "@sandbox19/harness";

/**
 * GET /products/:id, and every item inside a products page or search
 * result. Fields, exactly: `id` (number), `sku` (string), `name` (string),
 * `categoryId` (number), `sellerId` (number), `price` (number), `inStock`
 * (boolean), `scrapedAt` (an ISO-8601 timestamp string).
 */
export const ProductSchema = z.custom<HarnessProduct>(() => true); // TODO: replace with z.object({...})
export type Product = z.infer<typeof ProductSchema>;

/**
 * GET /me. Fields: `id` (number), `email` (string), `displayName`
 * (string), `role` (the literal union `"user" | "admin"`, not a bare
 * `string` -- narrow it with `z.enum` or a union of `z.literal`s).
 */
export const UserSchema = z.custom<HarnessUser>(() => true); // TODO: replace with z.object({...})
export type User = z.infer<typeof UserSchema>;

/**
 * The error envelope every non-2xx JSON response uses:
 * `{ error: { code: string, message: string } }`.
 */
export const ApiErrorSchema = z.custom<HarnessApiError>(() => true); // TODO: replace with z.object({...})
export type ApiErrorBody = z.infer<typeof ApiErrorSchema>;

/**
 * GET /products (cursor pagination): `{ items: Product[], nextCursor:
 * string | null }`. Build this from `ProductSchema`, not a fresh copy of
 * its fields -- `z.array(ProductSchema)` is the point of composing schemas.
 */
export const ProductsPageSchema = z.custom<{
  items: Product[];
  nextCursor: string | null;
}>(() => true); // TODO: replace with z.object({...}) built from ProductSchema
export type ProductsPage = z.infer<typeof ProductsPageSchema>;

/**
 * GET /categories/:id/summary: `{ categoryId: number, productCount:
 * number, avgPrice: number, inStockCount: number }`.
 */
export const CategorySummarySchema = z.custom<{
  categoryId: number;
  productCount: number;
  avgPrice: number;
  inStockCount: number;
}>(() => true); // TODO: replace with z.object({...})
export type CategorySummary = z.infer<typeof CategorySummarySchema>;

/**
 * GET /search: `{ items: Product[] }`. Build from `ProductSchema`, same as
 * `ProductsPageSchema`.
 */
export const SearchResultSchema = z.custom<{
  items: Product[];
}>(() => true); // TODO: replace with z.object({...}) built from ProductSchema
export type SearchResult = z.infer<typeof SearchResultSchema>;

/**
 * POST /auth/login and POST /auth/refresh both return this shape:
 * `{ accessToken: string, refreshToken: string }`.
 */
export const AuthTokensSchema = z.custom<{
  accessToken: string;
  refreshToken: string;
}>(() => true); // TODO: replace with z.object({...})
export type AuthTokens = z.infer<typeof AuthTokensSchema>;
