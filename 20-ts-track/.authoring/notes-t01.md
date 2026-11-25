# Authoring notes — 01-type-challenges (`@sandbox19/t01`)

## Challenge list (final)

| # | Challenge | Area | Difficulty |
|---|-----------|------|------------|
| 01 | `MyPick` | mapped type (given, unchanged) | warm-up |
| 02 | `DeepReadonly` | recursive mapped type (given, unchanged) | warm-up |
| 03 | `TupleToUnion` | indexed access (given, unchanged) | warm-up |
| 04 | `First`/`Last` | tuple destructuring via `infer` (given, unchanged) | warm-up |
| 05 | `EventByTag` + `assertNever` | conditional distribution + exhaustiveness typing (given, unchanged) | warm-up |
| 06 | `Getters` | mapped type + key remapping (`as`) | easy-medium |
| 07 | `PartialBy` | `keyof`-constrained generic | easy-medium |
| 08 | `ReplaceReturnType` | `infer` over a function type | medium |
| 09 | `MyAwaited` | conditional + `infer` + recursion | medium |
| 10 | `ExtractParams` | recursive template-literal parsing | medium-hard |
| 11 | `Flatten` | recursive tuple type | medium-hard |
| 12 | `Brand` + `UserId`/`ProductId` | nominal/branded types (capstone) | hardest |

Covers every SPEC area called out in design.md: mapped types with key
remapping (06), conditional types with `infer` (08, 09), template-literal
types (10), recursive types (09/10/11), branded/nominal types (12), and
generics with constraints (07, plus 01/04/05 already constrained).

## Files created

- `src/06-getters.ts` … `src/12-brand.ts` (7 new stub files)
- `src/index.ts` rewritten from `export {}` to `export * from "./NN-*"` for
  all 12 challenges (verbatim-module-syntax-safe: wildcard re-exports don't
  require the `type` keyword the way named re-exports of types do)
- `tests/01-my-pick.test-d.ts` … `tests/12-brand.test-d.ts` (12 type-level
  test files, all new — no `tests/` directory existed before)
- `tests/05-event-by-tag.test.ts`, `tests/12-brand.test.ts` (runtime vitest
  suites for `assertNever` and the branded-id constructors — satisfies the
  "test script must not be a no-op even after a correct solution" fix)
- `README.md`, `hints/hint-1.md`, `hints/hint-2.md`, `hints/hint-3.md`,
  `NOTES.md`

`package.json` and `tsconfig.json` were left untouched — `tsconfig.json`
already included both `src/**/*.ts` and `tests/**/*.ts`, so no fix was
needed there.

## Defect check on challenges 01–05

No defects found; left byte-identical. One point double-checked and
confirmed *not* a defect: challenge 05's `assertNever(value: unknown): never`
stub signature. The header comment explicitly says "type it so that... the
call compiles [only when exhaustive]" — the learner is expected to change
the parameter type from `unknown` to `never` as part of "implementing" the
challenge, not just fill in the body. Confirmed this is deliberate: on the
stock stub, the exhaustiveness `@ts-expect-error` test in
`tests/05-event-by-tag.test-d.ts` correctly fails as "unused directive"
(because `unknown` accepts the non-exhaustive `never`-violating call), and
on the reference solution (signature changed to `value: never`) it passes.

## Verification protocol — evidence

**(a) Stock gate.** Both validators exit non-zero on the committed stubs:

- `pnpm --filter @sandbox19/t01 run typecheck` → exit 1, 68 lines of output,
  all clean `TS2344: Type 'false' does not satisfy the constraint 'true'`
  (one per `Expect<Equal<...>>` failure) and `TS2578: Unused '@ts-expect-error'
  directive` (one per reject-case that no longer has anything to reject
  when the type is `unknown`).
- `pnpm --filter @sandbox19/t01 run test` → exit 1, 3 of 5 vitest
  assertions fail with `Error: not implemented` thrown from the `toUserId`/
  `toProductId` stubs in `src/12-brand.ts` (the `assertNever` runtime suite
  passes even on the stub, since "throws on any input" is true of the
  literal stub body too — that's fine per the brief, stock only needs to
  fail *cleanly*, not fail *every* assertion).

**(b) Pass-path proof.** Recorded `sha256sum` of all 13 `src/*.ts` files
before touching anything. Wrote throwaway reference solutions in place for
all 12 challenges (plus fixing `assertNever`'s signature as described
above). Both validators went fully green:

```
pnpm --filter @sandbox19/t01 run typecheck  -> EXIT 0
pnpm --filter @sandbox19/t01 run test       -> Test Files 2 passed (2), Tests 5 passed (5)
```

Then reverted every `src/*.ts` file back to the stub text and re-ran
`sha256sum -c` against the recorded baseline: all 13 files `OK` (byte-
identical). Re-ran both validators once more post-revert to confirm the
stock-fail behavior from (a) reproduces exactly (non-zero exit, same shape
of errors). No reference-solution text survives anywhere on disk — not in
`src/`, not in `hints/`, not in any scratch file (contamination sweep in
(d) confirms).

**(c) Anti-cheat spot checks (3 done, ≥2 required).**

1. `MyPick<T, K> = any` — every `Expect<Equal<...>>` instantiation in
   `tests/01-my-pick.test-d.ts` fails (`Equal` correctly distinguishes
   `any`), plus the excess-property reject-case becomes an unused-directive
   error. Confirms the "`Equal` distinguishes `any`" property design.md
   relies on.
2. `TupleToUnion<T> = 1 | 2 | 3` (hardcoded to satisfy exactly the first
   instantiation, `TupleToUnion<[1,2,3]>`) — that one instantiation
   incidentally passes, but the other four (`_Mixed`, `_Single`, `_Empty`,
   `_Readonly`) all fail. Confirms the "multiple distinct instantiations
   defeat a hardcoded answer" requirement.
3. `Brand<T, B> = T` (no actual branding) — both `NotEqual` checks in
   `tests/12-brand.test-d.ts` fail (`UserId` collapses to `number`, `UserId`
   collapses to `ProductId`), plus all three mixing reject-cases become
   unused-directive errors. Confirms the nominal-typing challenge actually
   requires a structural difference, not just a type alias.

All three reverted back to the reference solution, then to the stub, with
the same sha-verification discipline as (b).

**(d) Contamination sweep.** `grep -n "^export type" src/*.ts` shows every
challenge is still exactly `= unknown; // TODO: implement` (or the two
`Brand`/`UserId`/`ProductId` TODO variants). Grepped `hints/*.md` for `=`
lines outside the intentionally-pseudocode ` ```text ` blocks — none found;
hint-3's pseudocode blocks use prose/arrows (`->`, `for each ... :`) rather
than real TypeScript syntax, and are explicitly labeled non-copy-pasteable.
No stray scratch files were left inside the repo tree (checked `git status
--porcelain` after the whole exercise — only the expected new task files
are untracked).

## Gotchas hit during authoring

- **`interface` vs. `Record<string, unknown>` constraint.** First draft of
  challenge 06 constrained `Getters<T extends Record<string, unknown>>`.
  A `Getters<Person>` test case with `Person` declared via `interface`
  failed the constraint check itself (`TS2344: Index signature for type
  'string' is missing in type 'Person'`) — interfaces don't get the
  implicit string index signature that inline object-literal types do, so
  they're not assignable to `Record<string, unknown>` even though they're
  perfectly good "object with string keys" types. Fixed by relaxing the
  constraint to `T extends object`. Worth flagging to learners implicitly
  via the header comment, but not spelled out as a gotcha in the task
  README (would spoil the exercise) — filed here for future authors.
- **`Equal` (the HKT trick) does not treat an intersection type as
  identical to a structurally-equivalent flat object type, even when they
  are mutually assignable.** Discovered while writing the challenge 07
  reference solution: `Omit<T, K> & Partial<Pick<T, K>>` (the natural,
  correct answer) fails `Equal<..., { a?: X; b: Y }>` against a hand-typed
  flat expected shape — confirmed with a standalone probe file, and
  confirmed the failure isn't specific to that composition (a two-mapped-
  type-intersection alternative failed identically, as did `T & {}` for
  the `K = never` edge case). This is *why* the harness ships `Alike`
  alongside `Equal` — but `Alike` was verified (again via probe) to let
  `any` pass (`Alike<any, X>` is `true`, because the mutual-assignability
  fallback doesn't special-case `any`), so it is unsafe to use in a task
  test file per design.md's explicit "Equal distinguishes `any`" anti-cheat
  requirement. Resolution: rewrote challenge 07's tests to check
  per-property types via indexed access (`PartialBy<T,K>["someKey"]`,
  which resolves correctly through an intersection and *does* satisfy
  strict `Equal`) plus construction-based assignability checks for
  optionality (an object literal that omits exactly the widened keys must
  compile; one that omits an untouched key must not). This is a more
  robust pattern than whole-shape `Equal` for any challenge whose natural
  answer composes via `&`/`Omit`/`Pick` — worth keeping in mind for task 02
  and the capstone if similar composed-type assertions come up there.
- **`verbatimModuleSyntax` + `export *`.** Confirmed `export * from
  "./NN-challenge"` in `src/index.ts` compiles cleanly even for
  challenge files that only export types (e.g. `01-my-pick.ts`,
  `03-tuple-to-union.ts`) — wildcard re-exports aren't subject to the
  "must use `export type` for named type re-exports" rule that
  `verbatimModuleSyntax`/`isolatedModules` enforces for *named* re-exports
  (`TS1205`). No `export type *` needed anywhere.
- **`exactOptionalPropertyTypes` and indexed access.** Verified (via probe)
  that `T[K]` for an optional key `K` still widens to `Value | undefined`
  under `exactOptionalPropertyTypes` — the flag changes what you're allowed
  to *assign*, not what a read-position indexed access reports. This is
  what makes the challenge 07 per-property `Equal` checks
  (`TwoOfThree["host"]` equal to `string | undefined`) work as intended.
