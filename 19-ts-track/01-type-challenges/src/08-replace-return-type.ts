// Challenge 08 — ReplaceReturnType
//
// Given a function type `F` and a replacement return type `R`, produce a
// function type with exactly `F`'s parameter list (names, types, count,
// optionality) but return type `R`. Extract the parameter list with
// `infer`; do not hand-write it as `any[]` or `unknown[]`.
//
// ReplaceReturnType<(a: string, b: number) => boolean, string> ->
//   (a: string, b: number) => string

export type ReplaceReturnType<F extends (...args: any[]) => any, R> = unknown; // TODO: implement
