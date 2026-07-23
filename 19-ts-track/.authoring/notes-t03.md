# Authoring notes — 03-capstone-monorepo-contracts

Spoiler content for future generation/maintenance sessions. Same off-limits
rule as `design.md`: not for the learner.

## Package layout

- `@t3/contracts` (`packages/contracts/src/`): `product.ts` (Product,
  ProductPage, ListProductsParams, CategorySummary, SearchResult),
  `errors.ts` (ApiError), `jobs.ts` (JobKind, ProductEnrichJobV1,
  ProductRepriceJobV1, JobMessage discriminated union, ProductEnrichResult,
  ProductRepriceResult, JobResult discriminated union, JobError),
  `index.ts` barrel (`export *` from all three — safe under
  `verbatimModuleSyntax` since it's a mixed value/type re-export, not a
  type-only named re-export).
- `@t3/api` (`packages/api/src/`): `handlers.ts` — `ApiRequestError` (Error
  subclass wrapping a contract-typed `ApiError`, NOT itself a contract
  type) and `ApiHandlers`/`createApiHandlers(baseUrl)` covering
  `listProducts`/`getProduct`/`getCategorySummary`/`searchProducts` only.
  Deliberately left out `/auth/*` and `/me` (already covered by task 02;
  scoping capstone to the product/category/search surface keeps CP1 large
  enough to be meaningful without duplicating 02's lesson).
- `@t3/worker` (`packages/worker/src/`): `jobs.ts` — `receiveJobMessage`
  (safeParse + typed rejection, jobId-recovery rule pinned exactly: raw is
  a non-null object with a string `jobId` field, else null) and
  `processJob` (exhaustive switch + local `assertNever` helper — NOT
  exported, NOT from harness; this is deliberately worker-local so the
  exhaustiveness break happens inside `@t3/worker`'s own typecheck).
- `@t3/web` (`packages/web/src/`): `client.ts` — `ProductsPort` (duck-typed
  port interface, contracts-only types, no `@t3/api` import) and
  `createWebClient(port)`, which re-validates every port response with
  `ProductSchema.parse`/`ProductPageSchema.parse` before returning it.
  `@t3/web`'s `package.json` intentionally has no `@t3/api` dependency —
  `@t3/e2e` is the only package that imports both and wires
  `createApiHandlers(...)` into `createWebClient(...)`, relying purely on
  structural typing.
- `@t3/e2e` (`packages/e2e/`): `src/index.ts` stays `export {}` (unused
  placeholder, matches the skeleton). `tests/cp1.test.ts`,
  `tests/cp2.test.ts`, `tests/cp3.test.ts` are the GIVEN checkpoint suites.

## Deliverable-structure decision: contracts IS a learner stub

`@t3/contracts` ships with every schema as a `z.unknown()` placeholder and
every type as `z.infer<typeof ThatPlaceholder>` (= `unknown`). This was a
deliberate reading of the task: "define contracts ONCE" is explicitly part
of what the learner does in this capstone (mirrors how 02 has the learner
write the zod schemas from scratch) — contracts is not handed over
pre-solved. `api`/`worker`/`web` all have **fully and correctly typed**
signatures from day one (parameter/return types reference `@t3/contracts`
types directly), with only their function *bodies* as
`throw new Error("not implemented: ...")`. `JobKind` is the one exception:
it's a real, non-placeholder literal union (`"product.enrich" |
"product.reprice"`) from the start, because it's pure naming/scaffolding,
not schema-design content, and `@t3/worker`'s eventual exhaustive switch
needs something concrete to be exhaustive over independent of whether
`JobMessage` itself has been built out yet.

## Chosen stock-failure story

Documented in the capstone README's "On stock" section. Both signals fire,
for two different, both-clean reasons:

- `pnpm --filter @t3/e2e run typecheck` fails. Primary signal: hand-pinned
  `Expect<Equal<X, ExpectedLiteralShape>>` assertions in cp1/cp2 produce
  `TS2344: Type 'false' does not satisfy the constraint 'true'` at the
  exact line, because every `@t3/contracts` type currently resolves to
  `unknown`. Secondary/cascading: since `Product`/`ProductPage`/etc are
  `unknown`, ordinary runtime-test code in cp1/cp3 that does e.g.
  `page.items.map(...)` also fails to compile (`TS18046`, `TS7006`) — this
  is a *consequence* of the same root cause, not a separate bug; every
  message is still an ordinary, readable `tsc` diagnostic. One
  `@ts-expect-error` in cp1 (the `listProducts({ cursor: 123 })` reject
  case) also flips to "unused directive" (`TS2578`) on stock, since
  `ListProductsParams = unknown` accepts anything — this is the exact
  mechanism design.md's anti-cheat section describes for an
  over-permissive stub, verified live.
- `pnpm --filter @t3/e2e run test` fails separately, at runtime: every
  handler/`processJob`/`receiveJobMessage`/`createWebClient` call throws
  its own descriptive `not implemented: <fn>(<args>)` message; CP3's
  DESIGN.md gate fails with a specific missing-section/still-placeholder
  message. No unhandled rejections, no hung mock server — every test file
  starts its server in `beforeAll`/closes it in `afterAll`, which runs
  regardless of a test body throwing.
- `pnpm --filter @t3/contracts|api|worker|web run typecheck` are all
  green on stock — verified live, this is the actual "stub compiles,
  only the checkpoint fails" contract the deliverable-structure spec asks
  for.

## Exact validator commands (verified live against this workspace's pnpm
10 / vitest 4.1.10 / tsc 7.0.2)

```bash
cd 19-ts-track
pnpm --filter @t3/contracts run typecheck
pnpm --filter @t3/api run typecheck
pnpm --filter @t3/worker run typecheck
pnpm --filter @t3/web run typecheck
pnpm --filter @t3/e2e run typecheck
pnpm --filter @t3/e2e run test           # all three checkpoints
pnpm --filter @t3/e2e run test cp1       # one checkpoint file
pnpm --filter @t3/e2e run test cp2
pnpm --filter @t3/e2e run test cp3
```

**Gotcha found live**: `pnpm --filter @t3/e2e run test -- cp1` (with the
literal `--` before the filter arg, the pattern used elsewhere in this
repo/ecosystem) does **not** filter here — pnpm forwards both `--` and
`cp1` as separate positional args to the underlying `vitest run` command
(`vitest run "--" "cp1"`), and vitest does not treat that as a filename
filter; it ran the full suite (23/24 failing on stock, same as no filter
at all). Dropping the extra `--` (`pnpm --filter @t3/e2e run test cp1`,
args appended directly) filters correctly to one file. Documented this
exact distinction in the capstone README so a learner doesn't get a
confusing "my one checkpoint still shows other checkpoints' failures"
experience.

## zod resolution

`import { z } from "zod"` resolves fine from every `03-capstone-monorepo-
contracts/packages/*` package via plain Node/tsc upward directory walk to
the workspace root's `node_modules/zod` (root `package.json` declares
`zod` as a devDependency, shared through the workspace) — verified live
with both `tsx` and `tsc --noEmit` from `packages/contracts`. No package
needed `zod` added to its own `package.json` dependencies.

## Deterministic fixture values (seed `0xc0ffee`, harness default)

Captured live via a throwaway `tsx` probe script (not committed) that
started `startMockServer()` with no `seed` override and hit every route
CP1 exercises. Values baked into `cp1.test.ts`/`cp3.test.ts`:

- `GET /products/1` → `{ id:1, sku:"SKU-00001", name:"Rustic Apparatus 1",
  categoryId:7, sellerId:9, price:107.84, inStock:true,
  scrapedAt:"2024-01-01T01:00:00.000Z" }`
- `GET /products/42` → `{ id:42, sku:"SKU-00042", name:"Vintage Doohickey
  42", categoryId:1, sellerId:12, price:48.34, inStock:true,
  scrapedAt:"2024-01-02T18:00:00.000Z" }`
- `GET /products?limit=3` → items `[id1, id2, id3]`,
  `nextCursor:"aWQ6Mw"` (base64url of `"id:3"`)
- `GET /products?cursor=aWQ6Mw&limit=5` → items `[id4..id8]`
- `GET /categories/1/summary` → `{ categoryId:1, productCount:27,
  avgPrice:416.19, inStockCount:25 }`
- `GET /search?q=widget` → 23 items; first 3 (ascending id) are ids 5, 7,
  19
- `GET /products/9999` → 404 `{ error: { code:"not_found", message:"no
  product 9999" } }`

CP2's job-envelope fixtures are hand-designed, not derived from the mock
server — `product.enrich`/`product.reprice` are pure functions of their
payload, no server involved. Business rules pinned exactly in
`@t3/worker/src/jobs.ts`'s doc comment and mirrored in the README:
`normalizedSku = sku.trim().toUpperCase()`; `priceTier`: `<50` budget,
`<500` standard, else premium; `newPrice = round(currentPrice * (1 +
adjustmentPct/100), 2dp)`. Verified `49.99 * 1.2` rounds to `59.99` (not
`59.988` or `60`) live before pinning, to catch a rounding-direction bug
in either a reference or a learner implementation.

## Verification evidence

All of the following was run live from `19-ts-track/`, in order, and every
"revert" step was re-verified with `sha256sum -c` against a baseline
captured before any reference-implementation edits.

1. **Stock gate** — `contracts`/`api`/`worker`/`web` typecheck green;
   `e2e` typecheck fails with the `TS2344`/`TS18046`/`TS7006`/`TS2578`
   pattern above; `e2e` test run fails 23/24 (1 passes vacuously — see
   "Known vacuous-pass" below), no crashes, no hung server, no unhandled
   rejections.
2. **Pass-path** — sha256 of all 13 stub `.ts` files + `DESIGN.md` +
   `NOTES.md` (`NOTES.md` untouched throughout) + `README.md` +
   `hints/*.md` (17 files total) captured first. Wrote a full reference
   implementation in place across `contracts`/`api`/`worker`/`web` and a
   filled `DESIGN.md`. Result: all five `typecheck` commands green, all
   24 `e2e` tests pass. Re-ran `pnpm --filter @t3/e2e run test` a second
   time — identical result (`3 passed / 24 passed`), confirming
   determinism (fresh `startMockServer()` per file, no shared mutable
   state, no reliance on the second harness endpoint's monotonic clock
   beyond fixture generation itself). Then reverted every file
   byte-for-byte back to its original stub/template content and
   confirmed with `sha256sum -c`: **all 17 files OK**.
3. **Drift proof #1 (field rename)** — with the reference implementation
   in place, renamed `Product.price` → `Product.unitPrice` in
   `contracts/src/product.ts` only. `contracts`/`api`/`worker`/`web`
   typechecks all stayed green (none of them pattern-match on the
   `price` field name directly in this reference implementation's code
   paths). `@t3/e2e`'s typecheck failed at the hand-pinned
   `ExpectedProduct` comparison in `cp1.test.ts` (`TS2344` at the exact
   line). `pnpm --filter @t3/e2e run test cp1` also failed at runtime
   separately (5/7 failing) — `@t3/api`'s own `ProductSchema.parse` threw
   a `ZodError` because the live mock server still returns `price`, not
   `unitPrice`. Reverted the rename; both typecheck and cp1 test back to
   green.
4. **Drift proof #2 (exhaustiveness, the module's headline lever)** —
   added a third job kind, `"product.retag"`, to `JobKind` and to
   `JobMessageSchema`'s discriminated union in `contracts/src/jobs.ts`,
   touching nothing in `@t3/worker`. `pnpm --filter @t3/worker run
   typecheck` failed immediately: `TS2345: Argument of type '{ kind:
   "product.retag"; ... }' is not assignable to parameter of type
   'never'` at the `assertNever(job)` call inside `processJob`'s
   `default` branch — exactly the mechanism hint-2/hint-3 describe.
   Reverted; `@t3/worker` typecheck back to green.
5. **Negative control (CP3 anti-cast check)** — with the reference
   implementation in place, replaced `createWebClient`'s
   `ProductSchema.parse(...)`/`ProductPageSchema.parse(...)` calls with
   bare `as Product`/`as ProductPage` casts. `@t3/web`'s own typecheck
   stayed green (the cast is type-legal). `pnpm --filter @t3/e2e run
   test cp3` failed exactly one test — "a malformed value from the port
   is caught and rejected" — with `promise resolved "{ nope: true }"
   instead of rejecting`, confirming the check actually bites when
   validation is removed. Reverted; cp3 back to 5/5 passing.
6. **Full revert confirmation** — final `sha256sum -c` against the same
   17-file baseline: **all OK**. Final stock-gate re-run (typecheck ×5,
   test) reproduced the identical pass/fail pattern from step 1.

### Known vacuous-pass on stock (not a bug, documented for future sessions)

In `cp3.test.ts`, "a malformed value from the port is caught and
rejected, never silently cast through" passes on stock, vacuously:
`createWebClient`'s stub throws `not implemented` unconditionally, before
ever consulting `port`, so `fakeWeb.getProduct(1)` rejects regardless of
whether real validation exists yet. This doesn't weaken the checkpoint —
once a learner implements `createWebClient` for real (even with the
naive-cast bug from the negative-control test above), this specific test
starts actually discriminating, which is exactly what the negative-control
step above confirmed. Flagged here so a future session doesn't mistake the
one stock "pass" (`1 passed` in the `23 failed | 1 passed (24)` summary)
for a mistake in the checkpoint's design.

## Contamination sweep

`grep`ed all four stub packages' `src/` for `z.object(`, `discriminated
Union`, `z.literal`, `z.enum`, `z.array`, `fetch(`, `switch (`,
`assertNever`, `.parse(`, `.safeParse(` after the final revert — every
hit is inside a doc comment (naming the mechanism as guidance), never in
executable code. No stray files (probe/scratch `.ts` files used to
capture live fixture values were written under
`packages/contracts/src/` and deleted immediately after use — confirmed
absent in the final tree). `hints/*.md` code fences use deliberately
non-compilable pseudocode (informal conditionals like `if response.status
is not 2xx:`, elisions like `... handle it, return a result ...`) — the
one literal `z.object({ ...fields... })` fragment in hint-1 uses a literal
`...fields...` placeholder, not real field definitions. `DESIGN.md`
contains exactly 5 `[fill in` markers (one per section, none resolved).
`NOTES.md` contains exactly 3 `(fill in after completing the task)`
placeholders, one per section.

## Other gotchas

- Zod v4's `.optional()` infers a property type of `T | undefined`
  explicitly (not just "may be omitted") — under this workspace's
  `exactOptionalPropertyTypes`, a hand-written `ExpectedListProductsParams
  = { cursor?: string; limit?: number }` in `cp1.test.ts` is **not**
  `Equal` to the real zod-inferred type; it has to be written as
  `{ cursor?: string | undefined; limit?: number | undefined }` to match.
  Caught live via `pnpm --filter @t3/e2e run typecheck` while building
  the reference implementation, fixed in `cp1.test.ts` (this is a
  correction to the GIVEN checkpoint file itself, made before finalizing
  — not something a learner needs to work around).
- `Equal<unknown, ConcreteObjectShape>` does evaluate to `false` under the
  harness's HKT-trick `Equal` (verified live in isolation before relying
  on it for the whole stock-failure story) — `unknown` is not
  special-cased away the way it would be by a naive `X extends Y ? Y
  extends X ? true : false` check.
- `JSON.stringify`'s parameter type is `any` in lib.d.ts, so interpolating
  an `unknown`-typed stub parameter into a `not implemented: ...(${...})`
  message string works fine even before `@t3/contracts` is filled in —
  no extra `as` cast needed in the stub bodies.
