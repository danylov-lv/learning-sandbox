# Hint 2

**Schema composition.** `ProductsPageSchema` and `SearchResultSchema` both
contain a list of products -- don't write out the eight product fields a
second time inside them. `z.array(ProductSchema)` embeds one schema inside
another exactly the way `Product[]` embeds one type inside another, and the
inferred type follows automatically. This is the actual payoff of "types
come from schemas": get the leaf schema (`ProductSchema`) right once, and
every schema that contains a list of products inherits correctness from
it, at both the runtime-validation layer and the type layer, for free.

**`.optional()` vs `.nullable()`.** The server's `nextCursor` field is
always present in the response, but its value can be `null`. That's
`.nullable()` (the field exists, the value can be `null`), not
`.optional()` (the field itself might be entirely absent). Under this
workspace's `exactOptionalPropertyTypes`, confusing the two produces a real
type error the moment you try to assign a `null` where TypeScript expects
`undefined`, or vice versa -- read the error message's mention of "optional"
vs the value you're actually passing as the signal you picked the wrong one.

**`role` as a literal union.** `z.string()` accepts `"banana"`. The
harness's `User.role` is `"user" | "admin"`, nothing else. Zod narrows a
string to a fixed set of literal values via `z.enum([...])` or a union of
`z.literal(...)` calls -- either gets you a schema whose `z.infer` is the
literal union type, not `string`.

**The request core's shape**, in terms of what decides what:

- `!res.ok` decides whether you're on the error path at all.
- `res.status` (specifically `404` vs `401` vs everything else) decides
  *which* typed error class to construct on that path.
- `schema.safeParse(json)` on the success path decides between "return the
  validated, typed data" and "throw a validation error" -- and note that a
  `SdkValidationError` (or a raw `ZodError`) needs the *original* `ZodError`
  object attached if you want callers to see field-level detail, not just a
  string message.

**The refresh-retry pattern in `me()`.** This is "try once, and if it fails
for the *specific* reason that a retry could plausibly fix, try exactly
once more" -- not a loop, not a fixed number of attempts, and not blind
retrying regardless of *why* the first attempt failed. Structure it as:
attempt the request; if it throws the specific error type that means "the
access token was rejected," and only then, perform one refresh and attempt
the request again; any other error (or a second failure after the retry)
propagates immediately. Extracting "make the `/me` request with whatever
access token is currently stored" into its own small function makes this
much easier to call twice without duplicating the request-building logic.

**Seeding a client for the refresh test.** The given tests need a way to
construct a `MarketplaceClient` that already holds an invalid access token
paired with a valid refresh token, without waiting for a real token to
expire. That's what the constructor's `tokens` option (and `setTokens`) is
for -- design `me()`'s refresh trigger around "the stored access token was
rejected," not around any assumption about *how* it became invalid.
