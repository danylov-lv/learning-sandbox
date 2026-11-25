# Hint 3 — Workspace type flow: api, worker, web

## Direction

Once `@t3/contracts` is real, the other three packages' job is almost
entirely "call the right thing, then validate what comes back" — the
interesting design decisions are about *where* validation happens and
*what* gets thrown when it fails, not about inventing new shapes.

## Mechanism: `@t3/api`'s fetch-then-parse shape

Each `ApiHandlers` method follows the same skeleton:

```
async getProduct(id) {
  response = await fetch(`${baseUrl}/products/${id}`)
  body = await response.json()
  if response.status is not 2xx:
    parsedError = ApiErrorSchema.parse(body)   // or safeParse, your call
    throw new ApiRequestError(response.status, parsedError)
  return ProductSchema.parse(body)
}
```

The two `.parse()` calls are the entire point — `response.json()` alone
only gets you `any`, which happily lets a malformed body flow through
disguised `as Product`. `.parse()` is what turns "the network sent me
bytes" into "I have a value I can actually trust has this shape," and
throws a `ZodError` the instant it doesn't. `listProducts` is the same
shape but needs its params turned into a query string first (`limit`,
`cursor` — only include a key when it's actually present, given
`exactOptionalPropertyTypes`); `getCategorySummary` and `searchProducts`
are the same shape again against their own routes.

## Mechanism: `@t3/worker`'s pure functions

`receiveJobMessage` and `processJob` never touch the network — no
`fetch`, no `baseUrl`. That's deliberate: a job's payload already contains
everything `processJob` needs (see this task's exact business rules,
documented in `@t3/worker/src/jobs.ts`'s doc comment), so the function is
a pure computation from input to output, which is exactly what makes it
easy for CP2 to test with hand-picked inputs and hand-computed expected
outputs, no server involved at all.

## Mechanism: `@t3/web`'s port + re-validation

`createWebClient(port)` takes an already-constructed `port` (in practice,
whatever `@t3/api`'s `createApiHandlers(baseUrl)` returns — but
`@t3/web` never imports `@t3/api` to know that) and wraps each of its
methods:

```
async getProduct(id) {
  value = await port.getProduct(id)
  return ProductSchema.parse(value)
}
```

This looks redundant — `port.getProduct` already returns something typed
`Promise<Product>` — and that's exactly the lesson: the TypeScript type is
a compile-time promise only. `ProductSchema.parse(value)` is what makes
the promise true at runtime too, for a value that arrived through *any*
`ProductsPort`-shaped object, not just the specific one `@t3/api` happens
to build today. Without it, a `port` that lies (a bug, or — as CP3
constructs directly — a value cast past the type system with `as`) sails
straight through.

## Mechanism: why `@t3/web` never needs `@t3/api` in its `package.json`

`ProductsPort` is declared entirely in terms of `@t3/contracts` types.
`@t3/api`'s `ApiHandlers` interface happens to have methods with matching
names and (once contracts are filled in) matching parameter/return types —
so any value of type `ApiHandlers` is *also*, structurally, a valid
`ProductsPort`, with no explicit "implements" declaration needed anywhere.
This is ordinary structural typing, not a monorepo-specific trick — but it
is exactly what lets `@t3/e2e` (which depends on both) wire
`createApiHandlers(...)` straight into `createWebClient(...)` while
`@t3/web` itself stays decoupled from `@t3/api`'s existence.
