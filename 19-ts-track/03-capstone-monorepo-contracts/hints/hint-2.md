# Hint 2 — Versioned envelopes and exhaustive handling

## Direction

`JobMessageSchema` has to reject two different kinds of bad input for two
different reasons: an envelope whose `kind` isn't one this system knows
about at all, and an envelope whose `kind` it recognizes but whose
`version` it doesn't (yet, or anymore). Both need to fail validation — the
mechanism that makes both fail is the same one, not two separate checks
you write by hand.

## Mechanism: literal tags as the discriminant

`kind` and `version` on each per-kind schema aren't plain `string`/`number`
fields — they're each pinned to one exact value, a literal. `"kind":
"product.enrich"` only ever matches the literal string `"product.enrich"`,
nothing else that happens to also be a string; `"version": 1` only matches
the literal number `1`. Once every variant's `kind` (and `version`) is a
literal instead of a plain type, a union-of-object-schemas gets a
discriminant to key off of.

## Mechanism: discriminated union, not a plain union

A plain union of two object schemas has to try each member in order and
see which one happens to validate — slow, and it produces a confusing
error when nothing matches. A *discriminated* union is told up front which
field to switch on (`"kind"` here), so it can jump straight to the matching
variant's schema and validate only against that one. Zod's discriminated-
union constructor takes the discriminant field's name and the list of
per-kind variant schemas. Feed it `ProductEnrichJobV1Schema` and
`ProductRepriceJobV1Schema`.

Why this rejects a wrong version automatically, without any extra code:
an envelope with `kind: "product.enrich", version: 2` still selects the
`product.enrich` branch (by `kind`), but that branch's schema pins
`version` to the literal `1` — so the object fails to validate against
its own selected branch. No separate "check the version" step is needed;
it falls out of composing literals correctly.

## Mechanism: `assertNever` for exhaustiveness

This is a `@t3/worker`-side concern, in `processJob`, not a
`@t3/contracts`-side one. The shape:

```
function assertNever(x: never): never {
  throw new Error("unreachable: unhandled variant " + JSON.stringify(x));
}

function processJob(job) {
  switch (job.kind) {
    case "product.enrich":
      ... handle it, return a result ...
    case "product.reprice":
      ... handle it, return a result ...
    default:
      return assertNever(job);
  }
}
```

Inside the `default` branch, TypeScript narrows `job` to whatever's left
over after every `case` above has been excluded — if every kind is
handled, nothing is left over, so `job`'s narrowed type there is exactly
`never`, which is the only type `assertNever` accepts. Add a third kind to
`JobKind`/`JobMessageSchema` in `@t3/contracts` without adding a matching
`case` here, and the `default` branch's `job` is no longer narrowed all the
way to `never` — the call to `assertNever(job)` stops type-checking,
loudly, at that exact line. That's the mechanism; nothing about it is
specific to this task's two kinds, it works the same way for any
discriminated union with an exhaustive switch.

## Mechanism: `safeParse`, not `parse`, at the boundary

`receiveJobMessage` must never throw for bad input — so it can't call
`JobMessageSchema.parse(raw)` directly (that throws on failure). Zod's
`safeParse` variant returns a result object instead of throwing either
way: something like `{ success: true, data }` or `{ success: false,
error }`, letting you turn either outcome into this task's own
`{ ok: true, job }` / `{ ok: false, error }` shape without a `try`/`catch`
anywhere in this function.
