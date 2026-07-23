# 03 — Capstone: Monorepo Contracts

## Backstory

Your marketplace platform grew up. What started as one service is now a
small monorepo: an **api** layer that talks to the upstream marketplace, a
**worker** that enriches and reprices scraped products in the background,
and a **web** client that renders all of it. Each grew its own idea of
what a "Product" looks like — the api layer's `Product`, the worker's
`Product`, the web client's `Product` — and they've drifted, the same way
copy-pasted types always eventually drift: a field renamed in one place
and not the others, an optional field that's actually always present in
practice, a `price` that's a `number` in one file and a `string` fresh out
of `parseFloat` in another.

This capstone is the fix: pull every shared shape into one package,
**`@t3/contracts`**, and make every consumer import from it instead of
redeclaring it. `@t3/api`, `@t3/worker`, and `@t3/web` each depend on
`@t3/contracts` and nothing else shared between them — the dependency
graph itself is the enforcement mechanism, checked by `@t3/e2e`'s three
checkpoints.

## What's given

- **`@t3/contracts`, `@t3/api`, `@t3/worker`, `@t3/web`** — every package
  ships as a stub: full exported signatures (function names, parameter
  types, return types, interface shapes) with a doc comment above each one
  restating exactly what it must do, but every function body is
  `throw new Error("not implemented: ...")` and every `@t3/contracts`
  schema is a `z.unknown()` placeholder. Nothing here is optional
  boilerplate — every stub is the lesson.
- **`@t3/e2e`** — the GIVEN checkpoint suites, `tests/cp1.test.ts`,
  `tests/cp2.test.ts`, `tests/cp3.test.ts`. Do not edit them; they're the
  grader, not scratch space. `src/index.ts` is an unused placeholder.
- **`DESIGN.md`** at this directory's root — an unfilled template. CP3
  reads it directly off disk and fails until every section is filled in
  for real (see "Completion criteria").
- **`hints/hint-1.md` … `hint-3.md`** — direction and mechanism, never
  working code. Read them in order if you're stuck; each assumes the
  previous one's ground is already covered.
- **`NOTES.md`** — yours to fill in as you go, ungraded.

## Why this module is a pnpm workspace, not the usual per-task layout

See the module root's `README.md` and `.authoring/design.md`: this whole
track (`19-ts-track`) is a pnpm workspace instead of the repo's usual
Python/Docker layout, and that is a *documented exception*, not a
deviation. It matters especially here — a monorepo capstone about contract
drift needs an actual monorepo to happen in.

## What's required, checkpoint by checkpoint

### CP1 — contracts + api agree

Fill in every schema in `packages/contracts/src/product.ts` and
`packages/contracts/src/errors.ts` (see each file's doc comments for the
exact shape — `hints/hint-1.md` if you want the mechanism spelled out),
then implement `packages/api/src/handlers.ts`'s `createApiHandlers`: real
`fetch` calls against the four routes it wraps
(`GET /products`, `GET /products/:id`, `GET /categories/:id/summary`,
`GET /search?q=`), parsing every response body against the matching
`@t3/contracts` schema before returning it, and throwing a typed
`ApiRequestError` (carrying the parsed `ApiError`) on a non-2xx response.

CP1 checks two things independently:

- **At typecheck time** — that `ApiHandlers`' method signatures are
  literally expressed in `@t3/contracts` types (imported, not
  redeclared), and that the contracts themselves have the exact
  hand-pinned shape the checkpoint expects. A handful of
  `@ts-expect-error` lines confirm the handlers actually reject
  wrong-typed arguments, not just accept anything.
- **At test time** — a live `startMockServer()` (deterministic,
  `seed 0xc0ffee`, the harness's default), driving every handler and
  comparing results against values hand-computed independently of any
  code you write — never re-derived by calling your own handler a second
  way.

### CP2 — worker round-trip

Fill in `packages/contracts/src/jobs.ts`'s job-envelope schemas (the
discriminated union over `kind`/`version` — `hints/hint-2.md` covers the
mechanism), then implement `packages/worker/src/jobs.ts`:

- `receiveJobMessage(raw)` — validate an untyped value against
  `JobMessageSchema`. An unknown `kind`, a known `kind` with the wrong
  `version`, or a malformed payload must all come back as a typed
  `{ ok: false, error }` — **never throw**. The exact `jobId`-recovery
  rule for `error` is pinned in that file's doc comment.
- `processJob(job)` — an **exhaustive switch** over `job.kind`, computing
  each kind's result per the exact business rules documented above the
  function (sku normalization + price-tier classification for
  `product.enrich`, percentage-adjusted repricing for `product.reprice`).
  Use a `default` branch calling an `assertNever(x: never)` helper — see
  `hints/hint-2.md`. This is this checkpoint's anti-drift lever: add or
  rename a job kind in `@t3/contracts` without updating this switch, and
  `pnpm --filter @t3/worker run typecheck` fails at that exact line, not
  at some downstream test.

CP2 never starts a mock server — every job's payload carries everything
`processJob` needs, so it's tested as a pure function against hand-picked
inputs and hand-computed expected outputs.

### CP3 — web client end-to-end, plus a filled-in DESIGN.md

Implement `packages/web/src/client.ts`'s `createWebClient(port)`: wrap
every `port` method so its result is re-validated against the matching
`@t3/contracts` schema before being returned. This is the anti-cast check
— `port`'s TypeScript type already promises a valid shape, but that
promise is compile-time only; CP3 constructs a fake `port` that returns a
value cast past the type system with `as` and checks that `@t3/web` still
throws, not silently passes it through.

Separately, fill in `DESIGN.md` at this directory's root — five sections,
each with real analysis grounded in what you actually built (not generic
prose), each at least ~200 characters. CP3 reads the file off disk with
`node:fs` and fails with a specific missing-section or still-a-placeholder
message until it's done for real.

## Completion criteria

From `19-ts-track/`:

```bash
# typecheck every learner-written package (contracts/api/worker/web)
pnpm --filter @t3/contracts run typecheck
pnpm --filter @t3/api run typecheck
pnpm --filter @t3/worker run typecheck
pnpm --filter @t3/web run typecheck

# each checkpoint, standalone
pnpm --filter @t3/e2e run test cp1
pnpm --filter @t3/e2e run test cp2
pnpm --filter @t3/e2e run test cp3

# everything at once (also runs e2e's own typecheck, which encodes CP1's
# type-level assertions — a type-level failure there is as real a failure
# as a red checkpoint test)
pnpm --filter @t3/e2e run typecheck
pnpm --filter @t3/e2e run test
```

All of the above must exit 0. `pnpm --filter @t3/e2e run test cp1` (no
`--` before the filter argument) is the exact syntax that limits the run
to one checkpoint file — verified live against this workspace's pnpm/
vitest versions; `pnpm --filter @t3/e2e run test -- cp1` (with the extra
`--`) does not filter the same way here and runs every checkpoint.

### On stock (before you've written anything)

`pnpm --filter @t3/contracts|api|worker|web run typecheck` all pass — the
stubs are fully and correctly typed already, just unimplemented.
`pnpm --filter @t3/e2e run typecheck` fails, cleanly: every
`@t3/contracts` schema being `z.unknown()` makes `Product`, `ProductPage`,
`JobMessage`, etc. resolve to `unknown`, so CP1/CP2's hand-pinned
`Expect<Equal<..., ExpectedShape>>` assertions produce a direct
`TS2344: Type 'false' does not satisfy the constraint 'true'` at the exact
line, and code elsewhere in the checkpoints that tries to use those
`unknown`-typed values (e.g. `page.items.map(...)`) fails to compile too —
every message is a normal, readable `tsc` diagnostic, nothing cryptic.
`pnpm --filter @t3/e2e run test` separately fails at runtime: every
handler/`processJob`/`createWebClient` call throws its
`not implemented: ...` message, and CP3's `DESIGN.md` gate fails with a
message naming the still-unfilled section. No hung mock server, no
unhandled promise rejections — every test file starts its own server in
`beforeAll` and closes it in `afterAll` regardless of pass/fail.

## Estimated evenings

3–4. One checkpoint per evening is a reasonable pace; CP1 (contracts +
api) is the biggest single chunk, CP2 (worker) is the most self-contained,
CP3 (web + `DESIGN.md`) is short on code but the design memo deserves real
time.

## Topics to read up on

- zod: `z.object`, `.optional()`/`.nullable()`, `z.infer`,
  `z.discriminatedUnion`, `.parse()` vs `.safeParse()`
- TypeScript exhaustiveness checking over a discriminated union via a
  `never`-typed `default` branch
- `verbatimModuleSyntax`'s `import type` requirement and
  `exactOptionalPropertyTypes`'s effect on optional-field assignability
  (see the module root's `.authoring/design.md`-referenced gotchas — well,
  you can't read that file yet, but the module README's "strict compiler
  flags" list names them; work them out from `tsc`'s own error messages,
  same as any real strict-mode codebase)
- Structural typing / duck typing as a dependency-avoidance mechanism
  (`@t3/web`'s `ProductsPort`, see `hints/hint-3.md`)

## Off-limits

`.authoring/design.md` (at the module root) documents this task's grading
internals — spoilers, same rule as every other task in this module. Read
it after you've finished, if at all.
