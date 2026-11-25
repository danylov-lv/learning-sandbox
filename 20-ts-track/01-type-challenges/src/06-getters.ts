// Challenge 06 — Getters
//
// Given an object type `T` with string keys, produce a type with one
// zero-argument getter method per property: key `k` becomes
// `get${Capitalize<k>}`, returning the original property's value type
// unchanged. The original keys must not survive in the result — only the
// remapped `get*` names.
//
// Getters<{ name: string; age: number }> ->
//   { getName: () => string; getAge: () => number }

export type Getters<T extends object> = unknown; // TODO: implement
