# 19-ts-track — authoring design (spoiler contract)

Off-limits to the learner before finishing a task, same rule as every other
module in this repo. This document is for task-authoring agents and future
generation sessions.

## Module shape

This is a **TypeScript module built as a pnpm workspace**: no Python, no
`pyproject.toml`, no `uv.lock`, no `docker-compose.yml`, no host ports. The
workspace at `19-ts-track/` (root `package.json` + `pnpm-workspace.yaml` +
committed `pnpm-lock.yaml`) replaces all of that, exactly the way module
18-rust-track's Cargo workspace does. This is the module's documented
CONVENTIONS.md exception; state it as such when writing task READMEs.

All dev dependencies live once in the root `package.json` and are shared
through the workspace — task packages declare **no** dev dependencies of their
own, only a `workspace:*` link to `@sandbox19/harness` (and, in the capstone,
to sibling `@t3/*` packages). Task-authoring agents fill in each package's
`src/`, `tests/`, `README.md`, `hints/`, and `NOTES.md`; they must **not**
edit root dependencies or run `pnpm install` again.

Resolved versions (from the committed lockfile at generation time):
typescript **7.0.2**, zod **4.4.3**, vitest **4.1.10**, @types/node
**26.1.1**, tsx **4.23.1**.

Strict compiler flags (in `tsconfig.base.json`, extended by every package) —
the tasks lean on these, do not relax them:
`strict`, `noEmit`, `target ES2022`, `module ESNext`,
`moduleResolution "Bundler"`, `esModuleInterop`, `skipLibCheck`,
`forceConsistentCasingInFileNames`, `noUncheckedIndexedAccess`,
`exactOptionalPropertyTypes`, `types ["node"]`, `verbatimModuleSyntax`.

Author gotchas from these flags:

- **`verbatimModuleSyntax`** — a type-only import must be `import type` (or an
  inline `import { type X }`); a plain `import { X }` of a type is a compile
  error. Same for re-exports: use `export type`. The harness does this
  already; mirror it.
- **`noUncheckedIndexedAccess`** — `arr[i]` and `map access` are `T |
  undefined`; you must narrow before use. Test code that indexes response
  arrays needs a guard or a `as` with a justification.
- **`exactOptionalPropertyTypes`** — `{ x?: T }` is not assignable from
  `{ x: undefined }`. Build optional fields by omission, not by assigning
  `undefined`.
- Bundler resolution: intra-package imports are **extensionless**
  (`./mock-server`, not `./mock-server.ts`) unless you enable
  `allowImportingTsExtensions` (we did not).

## Grading contract (the module's documented exception)

The validator is `pnpm --filter <pkg> run typecheck` (`tsc --noEmit`, strict)
and/or `pnpm --filter <pkg> run test` (`vitest run`). A type error or a
failing test exits non-zero with a clean, human-readable message. This is the
module's stand-in for the repo-wide "print `NOT PASSED: <reason>` and exit 1,
no raw tracebacks" rule, and it is documented here as the one exception.

Because the message **is** the diagnosis:

- Every given `vitest` assertion carries a descriptive message
  (`expect(x, "why this must hold").toBe(...)` / a message arg), never a bare
  assertion whose failure says nothing.
- Every type-level assertion uses `Expect<Equal<Actual, Expected>>` (or
  `ExpectTrue`/`ExpectFalse`) so a wrong or `any` result produces the clean
  `TS2344: Type 'false' does not satisfy the constraint 'true'` at the exact
  line — a readable "this type is wrong" signal.
- `report.ts` (`notPassed`/`passed`) is available for any standalone
  validator script that wants the literal `NOT PASSED:` convention, but tasks
  should prefer tsc/vitest exit codes.

## Anti-cheat / verification philosophy (inherited from the rest of the repo)

- **Multiple instantiations.** Type-challenge tests must assert several
  distinct instantiations of the type under test, so an implementation
  hardcoded to satisfy one expected output fails the others. One
  `Expect<Equal<MyPick<Foo, 'a'>, {...}>>` is not enough; add cases with
  different keys, empty selections, and nested types.
- **`Equal` distinguishes `any`.** The exported `Equal` uses the HKT trick
  `(<T>() => T extends X ? 1 : 2) extends (<T>() => T extends Y ? 1 : 2)`, so
  a lazy `type Answer = any` stub does **not** satisfy
  `Expect<Equal<Answer, Concrete>>`. Verified in generation: `Equal<any,
  number>` is `false`. Rely on this.
- **Reject-cases via `@ts-expect-error`.** Where a type must *reject*
  something (a too-wide argument, an invalid key), assert it with a
  `// @ts-expect-error` line that only holds when the type is correctly
  restrictive — an over-permissive stub makes the suppressed line compile,
  which itself becomes an "unused `@ts-expect-error`" error.
- **Runtime validation via malformed routes.** The SDK task's `vitest` suite
  MUST hit the harness's deliberately-malformed routes (`/products/malformed`,
  `/products/wrongshape`). A non-validating implementation that does `return
  (await res.json()) as Product` passes the happy path but must **fail** the
  "malformed response must throw" test. A correct zod-validating client
  throws (`ZodError`) on those routes. This is the point of the task — do not
  omit those assertions.
- **Never grade against a re-derivation of the learner's own code.** Expected
  values are hand-authored or come from the harness's independently-generated
  fixtures, never from running the learner's function a second way.

## Harness API surface (`@sandbox19/harness`, `packages/harness/src/`)

Task-authoring agents write against these exact signatures. Depend on
`@sandbox19/harness`; do not re-implement any of it inside a task package.

```ts
// type-testing.ts — pure type-only module (import via `import type`)
export type Expect<T extends true> = T;
export type ExpectTrue<T extends true> = T;
export type ExpectFalse<T extends false> = T;
export type Equal<X, Y> =
  (<T>() => T extends X ? 1 : 2) extends (<T>() => T extends Y ? 1 : 2)
    ? true : false;
export type NotEqual<X, Y> = true extends Equal<X, Y> ? false : true;
export type IsAny<T> = 0 extends 1 & T ? true : false;
export type IsNever<T> = [T] extends [never] ? true : false;
export type IsUnknown<T> = IsAny<T> extends true ? false
  : unknown extends T ? true : false;
export type Alike<X, Y> = Equal<X, Y> extends true ? true
  : [X] extends [Y] ? ([Y] extends [X] ? true : false) : false;

// mock-server.ts — deterministic HTTP mock over node:http, no extra deps
export interface Product {
  id: number; sku: string; name: string; categoryId: number;
  sellerId: number; price: number; inStock: boolean; scrapedAt: string;
}
export interface User {
  id: number; email: string; displayName: string; role: "user" | "admin";
}
export interface ApiError { error: { code: string; message: string } }
export interface MockServer {
  readonly baseUrl: string; readonly port: number; close(): Promise<void>;
}
export function startMockServer(opts?: { seed?: number }): Promise<MockServer>;

// report.ts
export function notPassed(reason: string): never;  // "NOT PASSED: ..." -> exit 1
export function passed(msg?: string): void;
```

### Mock server behavior (what task tests can rely on)

Always binds `127.0.0.1:0` (ephemeral port — parallel `vitest` runs never
collide); read `baseUrl`/`port` off the returned handle; `await close()` to
stop. Data is generated from a fixed seed (default `0xc0ffee`, overridable via
`startMockServer({ seed })`) with an inlined mulberry32 PRNG — 200 products,
8 categories, 12 sellers, no faker/network. Endpoints:

- `GET /products?cursor=<opaque>&limit=<n>` → `{ items: Product[], nextCursor:
  string | null }`. Keyset pagination over ids 1..200, stable ascending order,
  default limit 20, capped at 100. `nextCursor` is an opaque base64url token;
  `null` on the last page.
- `GET /products/:id` → `Product`, or 404 `ApiError` (`code: "not_found"`).
- `GET /categories/:id/summary` → `{ categoryId, productCount, avgPrice,
  inStockCount }`.
- `GET /search?q=<term>` → `{ items: Product[] }` (case-insensitive name
  substring; empty `q` → empty list).
- `POST /auth/login` `{ email, password }` → `{ accessToken, refreshToken }`
  for the fixture user `buyer@example.com` / `hunter2`; else 401 `ApiError`.
- `POST /auth/refresh` `{ refreshToken }` → new `{ accessToken, refreshToken }`
  and **rotates** (the presented refresh token is invalidated); 401 on
  unknown/rotated tokens.
- `GET /me` with `Authorization: Bearer <accessToken>` → `User`; 401 without
  or with a bad token.
- **Malformed (validation-test targets):** `GET /products/malformed` →
  a product whose `price` is a STRING and whose `inStock` is MISSING;
  `GET /products/wrongshape` → `{ nope: true }`. Both return HTTP 200 with a
  schema-invalid body on purpose.

## The three tasks, in order

**01 — type-challenges** (`@sandbox19/t01`). A 12-challenge progression from
easy utility types (Pick, Readonly, tuple-to-union) up through conditional and
mapped types, recursion, and inference (e.g. a small `DeepReadonly`, a
`Router`-style path-param extractor). Each challenge lives with a `.test-d.ts`
of type-level assertions (`Expect<Equal<...>>`, `@ts-expect-error` reject
cases). Graded by `run typecheck`: solve in the types, and every challenge
must assert multiple instantiations so a hardcoded answer fails.

**02 — type-safe-sdk-client** (`@sandbox19/t02`). Build a client for the
marketplace API the harness serves: zod schemas for `Product`/`User`/errors,
types **inferred** from those schemas (`z.infer`), an auth flow with token
refresh, and cursor pagination (ideally an async-iterator over pages). Graded
by `run test` (vitest against a live `startMockServer()`): the happy paths
plus the mandatory malformed-route assertions that force real validation — a
naive `as Product` cast fails them.

**03 — capstone-monorepo-contracts** (`@t3/*`). `@t3/contracts` holds the
single source of truth (zod schemas + inferred types + shared error/DTO
definitions). `@t3/api` (a request handler layer over the contracts),
`@t3/worker` (a background consumer), and `@t3/web` (a typed client) each
import from `@t3/contracts` only. `@t3/e2e` holds the checkpoint suites:
**CP1** contracts + api agree, **CP2** worker round-trips a contract-typed
payload, **CP3** web client consumes api responses end-to-end — each a
`vitest` file (`cp1`/`cp2`/`cp3`). The grading lever is that a contract change
not propagated to a consumer breaks that consumer's typecheck or test; never
grade a package against its own re-derived output. Leave detailed task content
to the per-task authors — depend on `@sandbox19/harness`, never re-implement
it.
