// Challenge 07 — PartialBy
//
// Given object type `T` and a subset of its keys `K extends keyof T`, make
// exactly those keys optional. Every key outside `K` must keep its original
// required/optional status unchanged — unlike the built-in `Partial<T>`,
// which loosens every key.
//
// PartialBy<{ a: string; b: number; c: boolean }, "a" | "b"> ->
//   { a?: string; b?: number; c: boolean }

export type PartialBy<T, K extends keyof T> = unknown; // TODO: implement
