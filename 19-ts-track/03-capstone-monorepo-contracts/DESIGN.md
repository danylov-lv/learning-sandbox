# Capstone Design Memo — Monorepo Contracts

Fill in each section with your own analysis, grounded in what you actually
built and observed across CP1, CP2, and CP3 of this capstone — not generic
prose about zod or monorepos in the abstract. CP3's test suite reads this
file and checks that every section below is present, filled in, and long
enough to actually say something.

## Contract surface

[fill in — list every schema/type @t3/contracts exports and, for each, name
the consumer(s) that import it (@t3/api, @t3/worker, @t3/web). Where did you
draw the line between "this belongs in @t3/contracts" and "this is
implementation detail that belongs in the package that owns it" — for
example, is `ApiRequestError` a contract, or is it @t3/api's own concern
built on top of a contract? Why?]

## Versioning & evolution strategy

[fill in — walk through the job-message envelope's `kind` + `version`
design concretely. If you needed to ship a `product.enrich` v2 with an
extra field, what would you actually change, where, and what would stay
untouched? How does a v1 consumer that never gets updated behave when a v2
envelope shows up — does it reject cleanly, or does something worse happen?
Ground this in your own JobMessageSchema, not the general idea of API
versioning.]

## What breaks where when a contract changes

[fill in — pick one field-rename or job-kind-addition you actually tried
(or would try) against your own implementation, and trace it: which
package's `pnpm --filter <pkg> run typecheck` fails first, at which exact
line, and why? Which packages, if any, would NOT fail to typecheck but
would instead fail a runtime test — and why is that a weaker guarantee than
a typecheck failure?]

## Runtime vs compile-time guarantees

[fill in — TypeScript types are erased at runtime. Point to one concrete
place in your own @t3/web (or @t3/api) where you re-validate a value with a
zod `.parse()`/`.safeParse()` even though its TypeScript type already
"promised" the shape was correct, and explain what CP3's fake-port test
proved about why that re-validation has to be there. What's still only
enforced at compile time in your system, never at runtime, and is that a
gap you're comfortable with?]

## What I'd do differently in my real monorepo

[fill in — this capstone skips a lot a real monorepo would need: no actual
message queue for the worker, no auth on the api layer, no build/publish
step for @t3/contracts as a versioned package, no schema-compatibility CI
check. Pick at least two of those (or your own) and describe concretely
what you'd add first, and why that one first.]
