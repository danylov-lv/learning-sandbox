# 02 -- Type-Safe SDK Client

## Backstory

You maintain a handful of scrapers and internal integrations against a
marketplace API. Every one of them was written the fast way: `fetch(url)`,
`await res.json()`, `as Product`, ship it. It's worked fine until it
hasn't -- a field got renamed upstream, a "temporary" endpoint quietly
started returning `price` as a string, and one integration silently wrote
`NaN` into a billing report for two weeks before anyone noticed, because
nothing was ever checked at the boundary. `as Product` doesn't validate
anything; it just tells the compiler to stop asking questions.

This task is the fix: a client where the *types* are a byproduct of real
runtime validation, not a promise you make to the compiler and then break.
Every response gets checked against a schema before your code ever sees it
-- a well-formed response comes back fully typed, and a malformed one
throws immediately, with a message that says what was wrong, instead of
propagating a lie three layers deep into your codebase.

## What's given

- `src/schemas.ts`, `src/errors.ts`, `src/client.ts`, `src/index.ts` -- the
  scaffold. Every export has its final signature and a doc comment stating
  its exact contract; every schema is a `z.custom(() => true)` placeholder
  and every method body is `throw new Error("not implemented")`. Read the
  doc comments before writing anything -- they specify behavior the given
  tests rely on (which HTTP status becomes which error class, what `login`
  and `refresh` are expected to do to the client's stored tokens, etc.).
- `tests/*.test.ts` -- the vitest suite, run against a live
  `startMockServer()` from `@sandbox19/harness` (a real HTTP server on an
  ephemeral port, closed in `afterAll`). This is the grader; don't edit it.
- `tests/types.test-d.ts` -- type-level assertions, checked by
  `tsc --noEmit`. Also not to be edited.
- `@sandbox19/harness`, providing `startMockServer()` and the `Product`,
  `User`, `ApiError` types the mock server's responses are shaped like.

## The API you're building against

`startMockServer()` serves a small marketplace API in-memory, deterministic
from a seed (`0xc0ffee` by default -- the given tests pin exact values from
it):

- `GET /products?cursor=&limit=` -- cursor-paginated product listing.
  `limit` defaults to 20 server-side and is capped at 100 regardless of
  what you ask for. `nextCursor` is an opaque string, `null` on the last
  page.
- `GET /products/:id` -- a single product, or 404.
- `GET /categories/:id/summary` -- aggregate stats for a category.
- `GET /search?q=` -- case-insensitive substring match on product name; an
  empty `q` returns an empty list.
- `POST /auth/login` `{ email, password }` -- returns a token pair, or 401.
- `POST /auth/refresh` `{ refreshToken }` -- returns a **new** token pair
  and invalidates the one you presented (rotation, not reuse).
- `GET /me` with `Authorization: Bearer <accessToken>` -- the current user,
  or 401.
- `GET /products/malformed` and `GET /products/wrongshape` -- both return
  HTTP 200 with a body that is **not** a valid `Product`. They exist on
  purpose. See "the point of this task" below.

## What's required

1. **Schemas, not interfaces.** Every DTO type this package exports
   (`Product`, `User`, `ApiErrorBody`, `ProductsPage`, `CategorySummary`,
   `SearchResult`, `AuthTokens`) must be `z.infer<typeof SomeSchema>`.
   Writing the shape twice -- once as a hand-typed `interface` and again as
   a schema that happens to match it -- defeats the point: the schema *is*
   the source of truth, and the type is a byproduct of it.
2. **A generic, validated request core.** `MarketplaceClient#request(path,
   schema, init?)` is the one place an HTTP call actually happens and a
   response actually gets validated. Every typed method (`getProduct`,
   `listProducts`, ...) is a thin wrapper around it. On a 2xx response, a
   schema mismatch must throw a validation error -- never resolve with an
   unvalidated value. On a non-2xx response, translate the status code into
   one of the typed errors in `src/errors.ts`.
3. **Typed errors, not generic ones.** A 404 from a single-resource GET is
   `ApiNotFoundError`. A 401 is `ApiAuthError`. A schema mismatch is
   `SdkValidationError` (or you may let the underlying `ZodError` propagate
   directly -- both are accepted by the given tests, but a bare
   `new Error(...)` or an uncaught `ZodError` from deep inside a library
   internal is not the same thing as a class built for this).
4. **Cursor pagination and an async iterator.** `listProducts` wraps one
   page; `iterateProducts` walks every page in order via `nextCursor`,
   yielding one `Product` at a time, until it's exhausted.
5. **Auth with refresh.** `login` stores the returned tokens on the client.
   `refresh` rotates them. `me()` is the interesting one: on a 401, it must
   attempt exactly one `refresh()` and retry `/me` once with the new access
   token before giving up -- not zero retries, not a retry loop.

## The point of this task

`/products/malformed` and `/products/wrongshape` both return HTTP 200. A
client built as `return (await res.json()) as Product` will "succeed"
against both of them -- and hand its caller a `Product` whose `price` is a
string, or an object that isn't a product at all, both confidently typed as
if they were fine. The given tests hit these two routes directly through
your client's own `request(path, schema)` core and assert that the call
*rejects*. There is no way to pass that assertion with a cast. The schema
actually has to run, and actually has to reject bad data. That's the
difference this task is about.

## Completion criteria

From `19-ts-track/`:

```bash
pnpm --filter @sandbox19/t02 run typecheck
pnpm --filter @sandbox19/t02 run test
```

Both must exit 0. That means:

- Every schema-inferred type matches the harness's given DTO shapes, and
  the client's public methods reject the argument types they document
  (checked by `typecheck`, via `tests/types.test-d.ts`).
- Happy-path reads (`getProduct`, `listProducts`, `search`,
  `getCategorySummary`) return correctly-typed, correctly-valued data.
- `getProduct` on an unknown id rejects with `ApiNotFoundError`, not a
  `ZodError` and not a plain `Error`.
- Pagination respects `limit`, chains `nextCursor` correctly, and
  `iterateProducts` yields all 200 fixture products exactly once each, in
  ascending id order.
- `search` is case-insensitive and an empty query returns `[]`.
- `login`/`refresh`/`me` all behave as documented, including the
  refresh-rotation-invalidates-the-old-token behavior and `me()`'s
  single-retry-on-401 refresh path.
- `/products/malformed` and `/products/wrongshape`, requested through your
  client's generic `request` core, both reject with a validation error.

## Estimated evenings

2-3

## Topics to read up on

- zod schema design: `z.object`, `z.array`, `z.union`/`z.literal` for
  narrowing a string to a literal union, `.nullable()` vs `.optional()`
  (they mean different things), composing one schema from another
- `z.infer` and why deriving a type from a schema is a fundamentally
  different guarantee than writing the type by hand next to the schema
- Discriminated/typed error handling: designing an error class hierarchy so
  callers can `instanceof`-narrow instead of string-matching a `.message`
- Async iterators and generators (`async function*`, `for await...of`) as
  a way to expose "walk every page" without the caller managing cursors
- Structural vs nominal typing: why TypeScript will happily accept a
  same-shaped object in place of a "real" one, and why that's exactly the
  gap runtime validation exists to close
- `RequestInit`/the `fetch` API's response handling (`res.ok`, status
  codes, reading a body once)

## Off-limits until you're done

`.authoring/design.md` at the module root documents this task's grading
internals -- read it after you've passed both commands, if at all, not
before.
