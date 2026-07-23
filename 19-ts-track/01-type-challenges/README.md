# 01 — Type Challenges

## Backstory

Every library you've ever imported types for — the one where `Pick`,
`ReturnType`, or a router's `params` object "just knows" the right shape —
earned that by writing exactly the kind of code this task asks you to write.
This is a puzzle progression, not a scenario: twelve small type-level
problems, each solved entirely inside the type system, that build on each
other from a warm-up rebuild of `Pick` up to nominal ("branded") types.

## What's given

- `src/01-my-pick.ts` … `src/12-brand.ts` — twelve stub files, one per
  challenge. Each has a header comment stating the contract and an
  `export type X<...> = unknown; // TODO: implement` placeholder (challenge
  12 also has two throwing function stubs — see below). `src/index.ts`
  re-exports all twelve.
- `tests/01-my-pick.test-d.ts` … `tests/12-brand.test-d.ts` — the type-level
  assertions for every challenge, using `Expect<Equal<Actual, Expected>>`
  from `@sandbox19/harness` plus `@ts-expect-error` lines where a type must
  *reject* something. These files are never executed at runtime; `tsc`
  reading them is the point.
- `tests/05-event-by-tag.test.ts`, `tests/12-brand.test.ts` — a small
  `vitest` suite for the two challenges that also produce a runtime
  artifact (`assertNever`'s throw behavior, the branded-id constructors).
- `package.json` / `tsconfig.json` — already wired to
  `@sandbox19/harness` (`workspace:*`) and to the shared strict
  `tsconfig.base.json`; nothing to configure.

## What's required

Replace every `unknown` (and the two `throw new Error("not implemented")`
bodies in challenge 12) with a real implementation, so that both validators
below exit clean. Challenges 01–05 are meant to feel like a warm-up;
06–12 progressively combine mapped types, `infer`, template literals,
recursion, and branding — read each stub's header comment for the exact
contract before starting, and see `tests/NN-*.test-d.ts` for the precise
shapes your answer is held to (multiple instantiations per challenge, plus
`@ts-expect-error` lines that only compile if your type is *restrictive*
enough — a lazy `any` or an object type hardcoded to one example will fail
those).

## Completion criteria

From `19-ts-track/`:

```bash
pnpm --filter @sandbox19/t01 run typecheck   # tsc --noEmit, strict
pnpm --filter @sandbox19/t01 run test        # vitest run
```

Both must exit `0`. This task's grading contract is the module's documented
exception (see `19-ts-track/README.md` / `.authoring/design.md`): there is
no separate validator script, no "NOT PASSED" convention — the compiler
*is* the grader. A type error is the failure message; a passing
`typecheck` on a correct implementation means every `Expect<Equal<...>>`
resolved to `true` and every `@ts-expect-error` line actually has an error
to suppress.

## Challenge list

| # | Challenge | One-liner |
|---|-----------|-----------|
| 01 | `MyPick` | Rebuild the built-in `Pick<T, K>`. |
| 02 | `DeepReadonly` | Recursively `readonly`-mark a nested object. |
| 03 | `TupleToUnion` | Tuple element types → their union. |
| 04 | `First` / `Last` | First and last element types of a tuple. |
| 05 | `EventByTag` + `assertNever` | Narrow a discriminated union by tag; type an exhaustiveness guard. |
| 06 | `Getters` | Mapped type with key remapping (`as`): `name` → `getName: () => T`. |
| 07 | `PartialBy` | Generic with a `keyof`-constrained type param: widen only the selected keys. |
| 08 | `ReplaceReturnType` | `infer` over a function type: keep the params, swap the return type. |
| 09 | `MyAwaited` | Recursive conditional type: unwrap nested `Promise<Promise<...>>`. |
| 10 | `ExtractParams` | Recursive template-literal parsing: `"/a/:id/b/:bid"` → `{ id: string; bid: string }`. |
| 11 | `Flatten` | Recursive tuple type: flatten arbitrarily nested tuples. |
| 12 | `Brand` + `UserId`/`ProductId` | Nominal typing: two branded `number`s that must not be interchangeable. |

## Estimated evenings

1–2

## Topics to read up on

- Mapped types and key remapping via `as` (including `Capitalize<S>` and
  other intrinsic string-manipulation types)
- Conditional types and distributive conditional types (what happens when
  the checked type is a naked type parameter bound to a union)
- `infer` inside a conditional type — extracting a piece of a type instead
  of just testing it, both from object/array positions and from function
  parameter/return positions
- Recursive type aliases: how TypeScript allows a type to reference itself,
  and where the recursion depth limit bites
- Template literal types: pattern matching and decomposing string literal
  types, including recursive template-literal parsing
- Tuple types vs. array types, and manipulating tuples positionally
  (`[infer Head, ...infer Tail]`)
- Variance and assignability: why `Equal` (the HKT double-conditional
  trick) can tell `any` apart from a concrete type when a plain `extends`
  check can't
- Branded / nominal types: simulating nominal typing in a structurally
  typed language via an unused "phantom" property, and why the brand only
  exists at the type level (there is nothing to erase at runtime)
- Generic constraints (`K extends keyof T`) and how they narrow what a type
  parameter is allowed to be instantiated with

## Off-limits until you're done

`.authoring/design.md` at the module root documents this task's grading
internals — read it after both validators pass, if at all, not before.
