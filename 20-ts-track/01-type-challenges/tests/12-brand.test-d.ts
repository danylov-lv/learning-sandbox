import type { Expect, Equal, NotEqual } from "@sandbox19/harness";
import type { Brand, UserId, ProductId } from "../src/12-brand";
import { toUserId, toProductId } from "../src/12-brand";

type _BrandNotEqualToBase = Expect<NotEqual<UserId, number>>;
type _DistinctBrandsNotEqual = Expect<NotEqual<UserId, ProductId>>;
type _BrandUnderlyingIsNumeric = Expect<Equal<Brand<string, "Email">, Brand<string, "Email">>>;

function needsUserId(id: UserId): string {
  return `user:${id}`;
}

function needsProductId(id: ProductId): string {
  return `product:${id}`;
}

const userId = toUserId(1);
const productId = toProductId(1);

needsUserId(userId);
needsProductId(productId);

// @ts-expect-error — a raw number is not a UserId without going through toUserId
needsUserId(42);

// @ts-expect-error — a ProductId must not satisfy a UserId parameter, even though both are numbers underneath
needsUserId(productId);

// @ts-expect-error — the reverse mix must be rejected too
needsProductId(userId);
