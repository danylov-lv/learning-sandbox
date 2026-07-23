// Challenge 01 — MyPick
//
// Reconstruct the built-in `Pick`: given an object type `T` and a union of
// its keys `K`, produce the object type containing exactly those properties
// of `T`, with their original value types.

export type MyPick<T, K extends keyof T> = unknown; // TODO: implement
