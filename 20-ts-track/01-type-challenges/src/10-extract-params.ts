// Challenge 10 — ExtractParams
//
// Given a route path template using `:name` segments, produce an object
// type with one required `string` property per param name, in order of
// first appearance. A path with no `:name` segments yields `{}`. Params are
// delimited by `/` (or the end of the string) — parse recursively, one
// path segment at a time.
//
// ExtractParams<"/products/:id/reviews/:rid"> -> { id: string; rid: string }
// ExtractParams<"/health"> -> {}
// ExtractParams<"/users/:id"> -> { id: string }

export type ExtractParams<Path extends string> = unknown; // TODO: implement
