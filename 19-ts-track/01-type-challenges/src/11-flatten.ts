// Challenge 11 — Flatten
//
// Given a tuple type `T` whose elements may themselves be tuples (nested to
// any depth), produce a single flat tuple containing every leaf element, in
// left-to-right order. Non-tuple elements pass through as single leaves.
//
// Flatten<[1, [2, 3], [4, [5, 6]]]> -> [1, 2, 3, 4, 5, 6]
// Flatten<[]> -> []

export type Flatten<T extends readonly unknown[]> = unknown; // TODO: implement
