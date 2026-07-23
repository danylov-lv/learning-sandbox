// Challenge 12 — Brand
//
// `Brand<T, B>` attaches a compile-time-only "flavor" `B` to base type `T`,
// so two branded types built from the same runtime representation (e.g. two
// `number` ids) are NOT interchangeable at the type level, even though they
// are identical at runtime. Define `UserId` and `ProductId` as `number`
// branded with `"UserId"` and `"ProductId"` respectively, then implement
// `toUserId`/`toProductId` as the only sanctioned way to produce one from a
// raw `number` (a validated construction point, even though here it's a
// pure cast — no runtime representation change).

export type Brand<T, B extends string> = unknown; // TODO: implement

export type UserId = unknown; // TODO: Brand<number, "UserId">
export type ProductId = unknown; // TODO: Brand<number, "ProductId">

export function toUserId(id: number): UserId {
  throw new Error("not implemented");
}

export function toProductId(id: number): ProductId {
  throw new Error("not implemented");
}
