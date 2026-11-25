# Hint 1

Direction, not mechanism.

**01–05** are meant to feel familiar: they're the built-ins (`Pick`,
`Readonly`, tuple indexing) with the training wheels off, plus one
discriminated-union narrowing challenge. If any of these feel hard, that's
a signal to slow down before 06, not to guess.

**06–08** are all "reshape one level of an existing type." A mapped type
walks `keyof T` and rebuilds an object; `as` inside a mapped type lets you
change the *key*, not just the value, as you walk. `infer` inside a
conditional type is the same idea turned around: instead of building a new
key/value pair, you're asking the compiler to hand you back a piece of an
existing type (a function's parameter list, a promise's payload) so you can
reuse it verbatim in the result.

**09–11** all recurse. A recursive type alias is exactly like a recursive
function: a base case (stop condition) and a case that peels off one piece
and calls itself with what's left. Write the base case first and make sure
it's actually reachable — a recursive conditional type with no reachable
base case just as easily infinite-loops the compiler as recursive code
loops at runtime.

**12** asks you to fake something TypeScript doesn't have natively:
nominal types. Structurally, nothing stops two `number`s from being
interchangeable — so the trick has to *add* structure that doesn't exist at
runtime, purely to make the type checker see two `number`s as different
shapes.

If you get stuck on the *shape* of an answer rather than the mechanism,
that's what hint-2 is for.
