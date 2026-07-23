# Hint 1

Start from the one piece everything else depends on: `request(path, schema,
init?)`. Every typed method you write (`getProduct`, `listProducts`,
`search`, ...) should end up being a two-line wrapper around it -- build a
path (and maybe an `init`), call `request`, return what it gives you. If
you find yourself writing `fetch` and `.json()` inside `getProduct`
directly, stop and move that logic into `request` instead; the malformed-
route tests call `request` directly and expect it, specifically, to be the
thing that validates.

Think about the shape of `request`'s job in two independent halves, and
build them in order:

1. **Status code first.** Before you look at the body at all, decide what
   to do based on `res.ok` / `res.status`. A 404 becomes one error, a 401
   becomes another, anything else non-2xx becomes a third. This half
   doesn't need zod at all.
2. **Body validation second, only on the 2xx path.** Once you know the
   response was "successful" by HTTP's definition, that's when the schema
   gets to have an opinion about whether the body is actually usable.
   `schema.safeParse(json)` (not `.parse`) gives you a
   `{ success: true, data }` or `{ success: false, error }` object without
   throwing itself -- you decide what to do with the failure case.

Don't write any of the seven schemas as their final `z.object(...)` shape
until you've read the field list in each doc comment in `src/schemas.ts`
carefully -- in particular, `role` on `User` is not a plain string, and
`nextCursor` is nullable, not optional (those are different things in
zod, and the compiler flags in this workspace care about the difference).

For pagination and auth, don't design `iterateProducts` or `me()`'s retry
logic until `listProducts`/`login`/`refresh` individually work and you've
manually sanity-checked them (a quick throwaway script, or just running the
given tests file-by-file) -- both of those two methods are "call a simpler
method in a loop with a stopping condition," and that's much easier to get
right once the simpler method is trustworthy.
