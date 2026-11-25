# 02-type-safe-sdk-client — authoring notes

Off-limits to the learner (spoiler record), same rule as `design.md`. This
documents the generation/verification session for `@sandbox19/t02`.

## Src layout

- `src/schemas.ts` — every zod schema (`ProductSchema`, `UserSchema`,
  `ApiErrorSchema`, `ProductsPageSchema`, `CategorySummarySchema`,
  `SearchResultSchema`, `AuthTokensSchema`) plus their `z.infer`-derived
  type aliases. Stub bodies are `z.custom<ExactShape>(() => true)` — see
  "Stub design" below for why, not `z.unknown()`.
- `src/errors.ts` — `SdkError` (abstract base) and four concrete classes:
  `SdkValidationError` (wraps `ZodError`, field named `zodError` — NOT
  `cause`, to sidestep any interaction with `Error`'s built-in `cause?:
  unknown`), `ApiNotFoundError`, `ApiAuthError`, `ApiRequestError`.
- `src/client.ts` — `MarketplaceClient` with a public generic
  `request<T>(path, schema, init?)` core (the anti-cheat seam — tests call
  it directly against `/products/malformed` and `/products/wrongshape`),
  plus `getTokens`/`setTokens` (the refresh-testing seam — constructor
  also accepts `tokens?: AuthTokens` so a test can seed a garbage access
  token next to a valid refresh token without waiting for real expiry),
  `getProduct`, `listProducts`, `iterateProducts` (async generator),
  `getCategorySummary`, `search`, `login`, `refresh` (exposed publicly,
  not just used internally by `me()` — makes the rotation test cleaner),
  `me()` (single-retry refresh-on-401).
- `src/index.ts` — re-exports every schema/type/error/client symbol.
  Given tests import from `../src/index`, not individual files, so a
  broken re-export is itself a test failure.

## Stub design: `z.custom<ExactShape>(() => true)`, not `z.unknown()`

The task brief allows `z.unknown()` "ONLY if needed to keep typecheck
green on stock" and says to prefer a shape where stock typecheck passes
outright. `z.custom<T>(() => true)` achieves that fully: `z.infer` of it
is exactly `T` (the explicit generic parameter), so every stub schema's
inferred type already equals its final target type, and every given test
file (including `tests/types.test-d.ts`'s `Expect<Equal<...>>` /
`Expect<Alike<...>>` assertions) typechecks clean on stock — verified,
`tsc --noEmit` exits 0 with zero stub edits. At runtime the predicate
`() => true` accepts anything, so nothing is actually validated — proven
live: `ProductSchema.safeParse({ nope: true }).success === true` on the
stub. Since every `MarketplaceClient` method body is `throw new
Error("not implemented")`, the schemas never even get exercised at
runtime on stock anyway (every test fails at client construction or at
the first method call) — the `z.custom` trick's payoff is purely at the
typecheck layer, and it is strictly better there than `z.unknown()` would
have been (which would have cascaded `unknown`-typed failures through
every downstream method signature and every test file that touches a
field on the response).

The four "container" schemas (`ProductsPageSchema`, `CategorySummarySchema`,
`SearchResultSchema`, `AuthTokensSchema`) have no harness-exported TS
interface to pin against (only `Product`/`User`/`ApiError` are exported
from `@sandbox19/harness`), so their `z.custom<...>()` type parameter is an
inline anonymous object-literal type at the call site, not a named
interface — kept anonymous specifically so nothing resembling a
"reference interface" for these shapes is sitting in the file as a
target to blindly re-type.

## Pinned fixture values (verified live, seed `0xc0ffee`, default)

Verified via a throwaway script hitting a real `startMockServer()`
instance (raw `fetch`, no SDK) before writing any test:

- `GET /products/1` → `{ id: 1, sku: "SKU-00001", name: "Rustic Apparatus 1",
  categoryId: 7, sellerId: 9, price: 107.84, inStock: true, scrapedAt:
  "2024-01-01T01:00:00.000Z" }`.
- `GET /products/9999` → 404, `{ error: { code: "not_found", message: "no
  product 9999" } }`.
- `GET /products?limit=5` → ids `[1,2,3,4,5]`, `nextCursor` non-null;
  following it → ids `[6,7,8,9,10]`.
- `GET /products?limit=200` → capped server-side at 100 items (the mock
  server's documented `Math.min(rawLimit, 100)`), `nextCursor` non-null.
  Two consecutive `limit=100` pages (200 total) reach `nextCursor: null`.
  **This caught a bug in my own first draft of `pagination.test.ts`** — I
  initially asserted `limit: 200` returns 200 items in one page, which is
  wrong; fixed before the reference-impl pass (see below).
- `GET /categories/1/summary` → `{ categoryId: 1, productCount: 27,
  avgPrice: 416.19, inStockCount: 25 }`.
- `GET /search?q=widget` (and `WIDGET`, `WiDgEt`) → 23 items, same set
  regardless of case.
- `GET /search?q=` → `{ items: [] }`.
- `GET /products/malformed` → `price` as a string, `inStock` key absent.
- `GET /products/wrongshape` → `{ nope: true }`.
- Full keyset walk (`limit=37`, following `nextCursor` to `null`) → 200
  items, all unique ids, ascending, min 1 / max 200.
- Auth: bad creds → 401 `invalid_credentials`; good creds
  (`buyer@example.com` / `hunter2`) → `{ accessToken, refreshToken }`;
  `/me` with the access token → the fixture user; `/me` with a garbage
  token → 401 `unauthorized`; `/auth/refresh` with the refresh token →
  rotated pair; presenting the same (now-rotated-away) refresh token again
  → 401 `invalid_token`.

## Verification evidence

**Zod resolution:** confirmed both `tsx` (runtime) and `tsc --noEmit`
(typecheck) resolve `import { z } from "zod"` from inside
`02-type-safe-sdk-client/src/` with **no changes to the package's
`package.json`** — pnpm hoists the root `devDependencies` zod install to
the workspace root `node_modules/zod`, and Node/tsc module resolution
walks up from the task package to find it. Did not add zod as an explicit
dependency of `@sandbox19/t02`; task package.json is untouched from the
skeleton (`@sandbox19/harness` link only).

**Stock gate (a):** `run typecheck` exits 0 on stock (verified twice, no
edits between runs). `run test` exits 1 on stock: every one of the 18
given tests fails with `Error: not implemented` thrown from
`MarketplaceClient`'s constructor or (for the four auth tests that don't
construct in `beforeAll`) from the method call itself — clean stack
traces pointing at the exact stub `throw` line, no unhandled-rejection
spew, mock server always closes (all five suites' `afterAll` ran; the
suites whose `beforeAll` itself threw still ran `afterAll` since server
startup succeeded independently of client construction).

**Pass-path (b):** sha256'd all four `src/*.ts` files, wrote a reference
implementation in place (real `z.object`/`z.array`/`.nullable()`/literal-
union schemas in `schemas.ts`; a working `request`/`getProduct`/
`listProducts`/`iterateProducts`/`getCategorySummary`/`search`/`login`/
`refresh`/`me` in `client.ts`; `errors.ts` and `index.ts` untouched). Hit
one real `exactOptionalPropertyTypes` error on the first pass (see
Gotchas), fixed, then `run typecheck` → 0, `run test` → **18/18 passed**,
re-ran `run test` a second time with no changes → 18/18 again (determinism
confirmed, no flaky ordering/timing dependence). Reverted `schemas.ts` and
`client.ts` from the pre-edit backups; sha256 of all four files matched
the pre-edit hashes exactly (`schemas.ts` `ccf528ff…3646b1c`, `errors.ts`
`1d177399…2988a4bceb93`, `client.ts` `e9759e92…386b07f556d5f`, `index.ts`
`a6ae0c76…46d1fdd2779e` — untouched throughout, hashed anyway as a
belt-and-suspenders check). No reference implementation or backup file
survives anywhere; backups lived only in the OS temp scratchpad dir,
deleted after the sha256 comparison.

**Anti-cheat negative control (c):** with the reference implementation
still in place, replaced `request`'s validation tail (`schema.safeParse` /
throw-on-failure / return `parsed.data`) with a single `return json as T;`
(cast-only, zero validation) and reran `run test`: **exactly the two
`tests/validation.test.ts` cases failed** (`/products/malformed` and
`/products/wrongshape` both resolved instead of rejecting — the assertion
failure output shows the raw malformed/wrongshape bodies resolving
successfully), and **all 16 other tests still passed**. This is the
proof the suite actually forces real validation rather than merely
preferring it. Restored the real validation tail immediately after;
`run test` back to 18/18 before proceeding to the byte-identical revert.

**Contamination sweep (d):** grepped the task dir for `z.object|z.array|
safeParse|new ApiNotFoundError|new SdkValidationError|fetch\(` — only
hits are the doc-comment prose in `schemas.ts` describing what to replace
the stub with (`z.object`/`z.array` mentioned as guidance text, not as
code). No `.bak`/`_probe*`/`.orig` files anywhere under the task dir. `git
status --porcelain` on the task directory shows only the expected new
files (everything untracked, nothing modified-and-uncommitted from a
stray reference impl). Hints contain only prose/pseudocode blocks labeled
"you still have to turn this into working TypeScript yourself" — no
directly-pasteable implementation.

## Gotchas

- **`exactOptionalPropertyTypes` bit `iterateProducts`, not just
  `listProducts` itself.** Building the per-page options object as
  `{ limit: opts?.limit, cursor }` fails to typecheck against
  `listProducts`'s `{ limit?: number; cursor?: string | null }` parameter,
  because `opts?.limit` is `number | undefined` and an *explicit*
  `undefined` is not assignable to an optional `number` field under this
  flag. Fix: build the object by conditionally assigning the key
  (`if (opts?.limit !== undefined) pageOpts.limit = opts.limit;`) instead
  of always assigning a possibly-`undefined` value to it. Documented in
  `hints/hint-3.md`'s `iterateProducts` pseudocode as an explicit callout,
  since it's the one flag-interaction gotcha a learner is very likely to
  hit verbatim.
- **zod v4's `z.custom<T>(predicate?)` with no predicate, or a predicate
  that always returns `true`, validates nothing at runtime but still
  infers exactly `T`.** This is the load-bearing trick behind the whole
  stub design (see above) — confirmed live, not assumed from docs.
- **`verbatimModuleSyntax`** — every schema/type import in `client.ts` and
  every test file mixes value imports (schema constants, error classes,
  `MarketplaceClient`) with type-only imports (`AuthTokens`, `Product`,
  ...); used the inline `import { type X, ... }` form throughout rather
  than a separate `import type` statement, to match the harness's own
  style in `index.ts`.
- **`noUnusedLocals`/`noUnusedParameters` are NOT set** in
  `tsconfig.base.json` (only `strict` + the flags explicitly listed in
  `design.md`), so the stub's unused imports (every schema/error class
  imported into `client.ts` but never referenced inside `throw new
  Error(...)` bodies) do not fail `typecheck` — confirmed, this is why the
  stub can import everything the real implementation will need without
  the compiler complaining about it being unused yet.
- **`vitest run`'s default `include` glob
  (`**/*.{test,spec}.?(c|m)[jt]s?(x)`) does not match `*.test-d.ts`** —
  confirmed by reading `defaultInclude` out of vitest 4.1.10's own
  `dist/chunks/defaults.*.js`. `tests/types.test-d.ts` is therefore never
  executed by `run test`; it is checked purely by `run typecheck` via the
  package `tsconfig.json`'s `"tests/**/*.ts"` include glob, which is the
  intended split (type-level assertions graded by `tsc`, runtime behavior
  graded by `vitest`).
