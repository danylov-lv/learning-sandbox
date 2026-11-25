// Challenge 09 — MyAwaited
//
// Recursively unwrap a `Promise` type down to its ultimately-resolved,
// non-promise value type, following nested `Promise<Promise<...>>` chains
// as deep as they go. A non-`Promise` type passes through unchanged. This
// is a hand-written version of the built-in `Awaited<T>`.
//
// MyAwaited<Promise<string>> -> string
// MyAwaited<Promise<Promise<number>>> -> number
// MyAwaited<boolean> -> boolean

export type MyAwaited<T> = unknown; // TODO: implement
