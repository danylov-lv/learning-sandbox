**Tokenizer.** Track a single "current byte offset into the source" cursor
as you go; every `Token` you emit captures that cursor's value *before*
you consume the character(s) that make up the token. `char_indices()` (or
manually walking bytes/chars and re-deriving offsets) gives you exactly
this pairing of "byte position" and "character" without you having to
compute offsets by hand. For numbers, the trick to distinguishing `int`
from `float` at lex time is a single lookahead: consume a run of digits,
then check whether the *next* character is `.` and the one after *that*
is also a digit -- if so, keep consuming as a float; if the `.` isn't
followed by a digit, stop the number where it is and leave the `.` for
the next tokenizer step to reject (that's what makes `5.` invalid rather
than silently accepted). For keywords vs identifiers: lex the whole
identifier-shaped run first (`[A-Za-z_][A-Za-z0-9_]*`), *then* check the
resulting slice against the fixed keyword list (`"and"`, `"or"`, `"not"`,
`"true"`, `"false"`) -- don't try to special-case keyword characters
during the scan itself.

**Parser state.** A `struct Parser<'a> { tokens: Vec<Token<'a>>, pos:
usize }` (or similar) with `peek()`/`advance()`/`expect(kind)` helper
methods is the standard shape. Each grammar-tier function takes `&mut
Parser` (or `&mut self`), returns `Result<Expr, ParseError>`, and calls the
next-tighter tier's function for its operands. The `*` in an EBNF rule
like `additive := multiplicative (("+"|"-") multiplicative)*` becomes a
`loop` that keeps folding a new `Binary` node around the accumulator for
as long as it sees `+`/`-` next; the `?` in `comparison := additive
(comp_op additive)?` becomes a single `if`, not a loop, matching the "no
chaining" rule.

**Numeric tower.** Write one small private helper that takes two already-
evaluated `Value`s and a pair of closures (or match arms) for "both int"
vs "at least one float" -- every one of `+`, `-`, `*` needs this exact
same int-stays-int / float-promotes shape, so factoring it once saves you
writing the same four-way match three times. Division is the odd one out:
it doesn't need the int-vs-float split at all, since it *always* promotes
-- write it as its own smaller function that only needs to check "are both
operands numbers" and "is the divisor zero," then unconditionally works in
`f64`.

**Short-circuit `and`/`or`.** These are the one place evaluation order
matters beyond "left, then right, first error wins" -- write them as their
own explicit branch in the `Binary` match arm (checking `op` for `And`/
`Or` before you'd otherwise recurse into evaluating both sides), rather
than trying to fold them into the same generic "evaluate both sides, then
combine" shape every other binary operator uses.

**Builtins.** A `match name.as_str() { "min" => ..., "max" => ..., "round"
=> ..., _ => Err(UnknownFunction { .. }) }` inside your `Call` handling is
the whole mechanism -- resist making this generic/pluggable, there are
only three names and they're fixed by the spec.
