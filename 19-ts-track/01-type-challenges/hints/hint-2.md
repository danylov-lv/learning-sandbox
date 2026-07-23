# Hint 2

More specific mechanisms, grouped by challenge. Still no working type
definitions — the goal is "which TypeScript feature," not "which exact
characters."

**01 MyPick** — a mapped type `{ [P in K]: ... }` where the value side
indexes back into `T`.

**02 DeepReadonly** — a mapped type with the `readonly` modifier, whose
value side recurses: `T[P]` is either kept as-is (primitive/function) or
run back through `DeepReadonly` (object/array). You need a conditional to
tell those cases apart — checking against `object` is the usual first cut,
then special-casing function types so they don't get treated as plain
objects.

**03 TupleToUnion** — indexed access with `[number]` turns a tuple/array
type into the union of its element types directly; no recursion needed.

**04 First/Last** — a tuple can be destructured *as a type* the same way
you'd destructure it as a value: `[infer Head, ...infer Rest]` in a
conditional type's `extends` clause binds `Head`/`Rest` for the `true`
branch. `Last` is the same pattern read from the other end.

**05 EventByTag** — `Extract<T, U>` already does roughly this; the
exercise is writing the filtering conditional yourself, distributing over
the union `Events` by indexing each member's `tag` against `Tag`.
`assertNever`'s type signature (not its body) is what makes the
exhaustiveness check work — think about what parameter type makes it only
callable when nothing is left to call it with.

**06 Getters** — a mapped type over `keyof T`, remapped with `as`:
`` [K in keyof T as `get${...}`]: ... ``. `Capitalize<S>` needs a
string-literal type, so the key you're capitalizing has to be coerced to
one first (`K & string` if `K` isn't already known to be a string).

**07 PartialBy** — think of it as two disjoint slices of `T` glued back
together: the keys in `K` need `Partial`-style optionality, the keys not in
`K` need to stay exactly as they were. `Omit`/`Pick` (or their manual
mapped-type equivalents) plus an intersection `&` combine two shapes into
one.

**08 ReplaceReturnType** — a conditional type whose `extends` clause is a
*function type* containing `infer` in the parameter position:
`F extends (...args: infer A) => any ? ... : never`. Once you have `A`
(the inferred parameter tuple), you rebuild a function type from it with
the new return type.

**09 MyAwaited** — a conditional type whose `extends` clause is
`Promise<infer U>`; the recursive case is calling `MyAwaited<U>` again
instead of returning `U` directly, so nested promises keep unwrapping.

**10 ExtractParams** — a conditional type over a template literal pattern:
`` Path extends `${infer _Prefix}:${infer Param}/${infer Rest}` `` peels
off one param when there's more path after it; a second, simpler pattern
(no trailing `/`) handles the last param. Each successful match both
contributes a key to the result *and* recurses on what's left — this is
the same "peel one, recurse on the rest" shape as 04 and 11, just over
strings instead of tuples.

**11 Flatten** — same shape as `First`/`Last`'s destructuring, but each
element might itself need flattening: `[infer Head, ...infer Rest]`, where
`Head` is spread into the result differently depending on whether it's
itself an array/tuple. Spreading a type inside a tuple literal
(`[...A, ...B]`) is legal in a type position exactly like in a value
position.

**12 Brand** — an intersection type: the real type `T`, intersected with an
object type that has one property nobody will ever actually construct (a
unique symbol-keyed or specially-named field, holding `B`). Nothing reads
or writes that property at runtime — its only job is to make the
intersection structurally distinct from plain `T` and from a
differently-branded version of `T`. The constructor functions get there via
a type assertion, not a real transformation.
