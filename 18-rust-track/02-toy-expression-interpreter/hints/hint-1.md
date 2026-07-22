Build this in three genuinely separate passes, and get each one fully
working (with its own quick manual checks, even before `tests/` passes)
before moving to the next: tokenize, then parse, then evaluate. Resist the
urge to parse directly from the raw string, or to evaluate while parsing --
it's tempting for a language this small, but the whole point of the task
is the three-stage pipeline, and the tests exercise each stage's
observable behavior (a specific `Token` stream, a specific `Expr` tree
shape, a specific `Value`) somewhat independently.

Start with `tokenize`. Read every test in `tests/errors.rs` before writing
a single line of it -- the exact set of characters/character-sequences
that are and aren't valid tokens, and exactly which position gets reported
for each kind of lexical failure, is fully pinned there and in the
README's "Parse errors" table. Get `tokenize` producing the right stream
of `Token`s (right `TokenKind`, right `Position`) for a handful of
expressions by hand before you write any parsing logic at all -- a broken
tokenizer under a correct-looking parser produces very confusing failures.

For the parser, look at the EBNF grammar in the README as a literal
recipe: each named rule (`or_expr`, `and_expr`, `not_expr`, `comparison`,
`additive`, `multiplicative`, `unary`, `primary`) wants to become one
function, and each rule's body -- reading the `|` and `*`/`?` in the EBNF
-- tells you almost mechanically what that function's control flow looks
like. This EBNF-to-function correspondence is the standard shape of a
recursive-descent parser; it's worth understanding *why* it produces
correct precedence (rather than just copying it) before you write it, but
once you see why it works, each function is genuinely short.

Don't reach for any parsing library or a hand-rolled Pratt/precedence-
climbing parser unless you already know one and prefer it -- plain
recursive descent following the grammar tiers is enough for this
language's precedence table, with no operator-precedence table data
structure needed at all.
