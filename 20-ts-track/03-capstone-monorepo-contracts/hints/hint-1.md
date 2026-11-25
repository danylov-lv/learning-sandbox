# Hint 1 — Single source of truth in @t3/contracts

## Direction

Every `z.unknown()` placeholder in `packages/contracts/src/*.ts` needs to
become a real zod object schema, with the type derived from it via
`z.infer`, never written by hand alongside it. If you ever find yourself
writing both a zod schema AND a hand-written `interface`/`type` for the
same shape, you've reintroduced the exact duplication this capstone exists
to remove — one of the two will silently drift from the other the first
time either one changes.

## Mechanism: schema-first, type derived

The pattern for every exported pair in this package is the same shape,
mechanically:

```
export const XSchema = z.object({ ...fields... });
export type X = z.infer<typeof XSchema>;
```

Nothing about `X` is ever written directly — it falls out of `XSchema`
entirely. This is why `z.infer` matters: it's the mechanism that makes
"one definition" actually true, instead of just a convention two
definitions happen to follow today.

## Mechanism: matching a fixed shape exactly

Each schema's doc comment in the stub spells out the exact field set and
types — treat that the same way you'd treat a wire-format spec pinned
elsewhere in this repo. A zod object schema is built field by field, each
value a smaller schema for a primitive (string, number, boolean) or a
nested shape. Reach for:

- a schema for a plain string field
- a schema for a plain number field (some fields in this task's fixtures
  are always non-negative or always positive — deciding whether to encode
  that constraint into the schema, versus leaving it as a plain number, is
  your call; both let CP1 pass, only one catches a negative price as
  invalid at the boundary)
- a schema for a plain boolean field
- an array-of-schema for a list of items (e.g. a page's `items`)
- a nullable variant for a field that is a string in most cases but can
  legitimately be `null` (a page's `nextCursor` on the last page)
- an optional variant for a field that may be entirely absent from the
  object (the pagination params' `cursor`/`limit`)

## Gotcha: `exactOptionalPropertyTypes`

This workspace's `tsconfig.base.json` has `exactOptionalPropertyTypes` on.
Verify (small standalone `.ts` file, `tsc --noEmit`) what shape zod's
"optional" schema helper infers for an object field — specifically,
whether `{ cursor: undefined }` type-checks as an assignable value for the
inferred type, before you build `ListProductsParamsSchema` around it. If it
doesn't, you'll see the mismatch the moment `@t3/api`'s handler tries to
construct a params object by omission vs. by explicit `undefined`.

## Mechanism: the job envelope's payload nesting

`ProductEnrichJobV1Schema` and `ProductRepriceJobV1Schema` each have a
`payload` field that is itself an object schema, not a flat field. Build
the inner object schema first (as its own expression or `const`), the same
way you'd build `ProductSchema` — then use it as the value for the outer
schema's `payload` key. Nothing new here beyond composing schemas you
already know how to write; the only new idea is that composition works the
same way one level down.
