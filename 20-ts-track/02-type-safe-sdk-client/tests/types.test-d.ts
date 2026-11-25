// Given test -- do not edit. Type-level assertions, checked by
// `tsc --noEmit` (the `typecheck` script); this file is never executed.
// `declare const` values below exist only for their types.

import type {
  Product as HarnessProduct,
  User as HarnessUser,
} from "@sandbox19/harness";
import type { Alike, Equal, Expect } from "@sandbox19/harness";
import type {
  AuthTokens,
  CategorySummary,
  Product,
  ProductsPage,
  SearchResult,
  User,
} from "../src/schemas";
import type { MarketplaceClient } from "../src/client";

// --- the schema-inferred DTO types must match the harness's given shapes ---
// `Alike` (not `Equal`) tolerates optionality/readonly differences a valid
// zod schema might legitimately introduce; it still rejects a genuinely
// wrong shape (extra/missing/mistyped fields), and -- like `Equal` -- an `any`
// escape hatch does not satisfy it either.
type _ProductMatchesHarness = Expect<Alike<Product, HarnessProduct>>;
type _UserMatchesHarness = Expect<Alike<User, HarnessUser>>;

// --- container schemas must nest the DTO types correctly, not `any`/`unknown` ---
type _PageItemsAreProducts = Expect<Equal<ProductsPage["items"][number], Product>>;
type _PageCursorIsNullableString = Expect<Equal<ProductsPage["nextCursor"], string | null>>;
type _SearchItemsAreProducts = Expect<Equal<SearchResult["items"][number], Product>>;
type _SummaryShape = Expect<
  Equal<
    CategorySummary,
    { categoryId: number; productCount: number; avgPrice: number; inStockCount: number }
  >
>;
type _TokensShape = Expect<
  Equal<AuthTokens, { accessToken: string; refreshToken: string }>
>;

// --- method signatures must reject the wrong argument shapes ---
declare const client: MarketplaceClient;

// @ts-expect-error -- id must be a number, not a numeric string
void client.getProduct("7");

// @ts-expect-error -- limit must be a number, not a numeric string
void client.listProducts({ limit: "10" });

// @ts-expect-error -- categoryId must be a number, not a numeric string
void client.getCategorySummary("1");

// @ts-expect-error -- login takes two string arguments, not an options object
void client.login({ email: "a@b.com", password: "x" });

// @ts-expect-error -- request's second argument must be a ZodType, not an arbitrary object
void client.request("/products/1", { parse: () => undefined });

// Control: the well-typed calls above must NOT be flagged as errors -- if
// they were, every `@ts-expect-error` above it would be "unused" instead,
// which is itself a compile error and would catch an over-permissive stub.
void client.getProduct(7);
void client.listProducts({ limit: 10 });
void client.getCategorySummary(1);
void client.login("a@b.com", "x");
