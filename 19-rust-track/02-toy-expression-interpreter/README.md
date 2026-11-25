# 02 -- Toy Expression Interpreter

## Backstory

The platform this repo has been building throughout the other modules
(scraped products, per-record pricing, filter rules) has a recurring
operational headache: every client wants slightly different pricing logic
and slightly different filter rules, and today those live as `if`/`else`
chains buried in application code. Every new client means a code change, a
review, a deploy. Product wants client-configurable rules instead: a client
uploads a small text expression like

```
(price * 1.15) - (has_coupon and 5 or 0)
```

or a filter rule like

```
category == "electronics" and price < 500 and in_stock
```

and the platform evaluates it once per record, against that record's
fields, with no redeploy. That means the platform needs an actual
expression language: something to tokenize, parse into a tree, and
evaluate against a per-record environment -- a small compiler pipeline,
not a toy for its own sake. This task builds exactly that pipeline, scoped
down to a single evening-sized language, but with the same three stages
(lexer, parser, evaluator) a real rule engine would have.

This is also this module's dedicated showcase for Rust's enum-and-`match`
idiom: the abstract syntax tree is not a class hierarchy with virtual
dispatch, it's a plain `enum` with a `Box<Expr>` for recursive cases, and
every stage that consumes it is an exhaustive `match` the compiler checks
for you -- add a variant, and every non-exhaustive `match` in the crate
becomes a compile error until you handle it.

## What's given

- `src/lib.rs` -- **scaffold only**. It declares every public type this
  task's tests use as its graded API: `Token`/`TokenKind` (with a lifetime
  borrowing the source `&str`), `Expr`, `UnaryOp`, `BinaryOp`, `Value`,
  `Env`, `ParseError`, `EvalError`, and the top-level functions
  (`tokenize`, `parse`, `eval`, `eval_source`). Declaring these types *is*
  part of the contract -- their variants are what the tests construct and
  match against. Every function body is `todo!()`. You write all the
  logic; the shapes are fixed.
- `tests/` -- the full validator (see below). Read it before you start
  writing the tokenizer; the tests are, in aggregate, a more precise
  specification than any prose could be.
- The full language grammar and evaluation semantics, spelled out below in
  this README. This is the one and only place the semantics are defined --
  if the README and your intuition disagree, the README wins, because
  that's what the tests were written against.

## What's required

Implement, in `src/lib.rs`:

1. **`tokenize`** -- turns a `&str` into a `Vec<Token<'_>>`, or a
   `ParseError` at the position of the first character that doesn't start
   any valid token.
2. **`parse`** -- tokenizes and runs a recursive-descent parser producing
   a single `Expr` tree, or a `ParseError`. `parse` must also reject
   trailing input: if a complete expression is parsed but tokens remain
   before EOF, that's `ParseError::TrailingInput` at the first leftover
   token's position, not a silently-ignored suffix.
3. **`eval`** -- walks an `&Expr` against a supplied `&Env` (variable
   environment) and produces a `Value`, or an `EvalError`.
4. **`eval_source`** -- convenience: `parse` then `eval`, unifying both
   error types into `InterpError` via `From`.

## The language

### Grammar (EBNF)

Precedence from loosest to tightest binding (i.e. `or` binds loosest,
`primary` binds tightest -- read the list top to bottom as "each rule's
operator binds tighter than the one above it"):

```
expr          := or_expr

or_expr       := and_expr ( "or" and_expr )*
and_expr      := not_expr ( "and" not_expr )*
not_expr      := "not" not_expr
               | comparison

comparison    := additive ( comp_op additive )?
comp_op       := "==" | "!=" | "<" | "<=" | ">" | ">="

additive      := multiplicative ( ("+" | "-") multiplicative )*
multiplicative:= unary ( ("*" | "/") unary )*
unary         := "-" unary
               | primary

primary       := int_literal
               | float_literal
               | string_literal
               | "true" | "false"
               | ident "(" arg_list? ")"     ; function call
               | ident                        ; variable reference
               | "(" expr ")"

arg_list      := expr ( "," expr )*

int_literal   := digit+
float_literal := digit+ "." digit+
ident         := (alpha | "_") (alpha | digit | "_")*
```

Notes on the grammar itself, not just its shape:

- **Comparisons do not chain.** `comparison` allows at most *one*
  `comp_op` -- `a < b < c` is not "chained" the way it might read in
  ordinary math. It parses `a < b` as a complete comparison, and the
  second `< c` is unconsumed *trailing input*, which `parse` rejects with
  `ParseError::TrailingInput` positioned at the second `<`.
- **`not`, unary `-`, `and`/`or` all right-stack.** `not not true`,
  `- - -5`, and `a and b and c` (left-associated via the `*` in the EBNF
  for `and_expr`) are all valid; `not` and unary `-` themselves are
  right-recursive (`not_expr := "not" not_expr`, `unary := "-" unary`) so
  they stack without limit on a single operand.
- **No exponent/scientific notation, no leading `+` sign, no bare `.5` or
  `5.`.** A float literal requires at least one digit on both sides of the
  `.`. Numbers are never signed at the lexer level -- `-5` is always
  *unary minus applied to the literal `5`*, two tokens, not one signed
  numeric token.
- **No comments.** There is no comment syntax in this language at all.
- **Keywords are reserved and case-sensitive.** `and`, `or`, `not`,
  `true`, `false` are keywords, not identifiers -- you cannot declare a
  variable named `and`. `And`/`AND`/`True` are *not* keywords; they
  tokenize as ordinary identifiers.
- **Whitespace** (space, tab, `\n`, `\r`) separates tokens and is
  otherwise insignificant.
- **String literals** are double-quoted (`"like this"`) and support
  exactly four escapes: `\"`, `\\`, `\n`, `\t`. Any other character after
  a backslash, or a string with no closing `"` before the input ends, is
  an error (see below). Strings cannot span a literal newline without
  `\n`.

### Token positions

Every `Token` carries a `Position` -- the **byte offset** (0-based, into
the original `&str`, *not* a char index) of the token's first byte. For an
identifier, number, or string literal this is the first character; for a
keyword or operator, the first character of the operator. `Position` for
an end-of-input condition is `source.len()` -- one byte past the last
real byte.

### AST

`Expr::Var`, `Expr::Unary`, `Expr::Binary`, and `Expr::Call` all carry a
`Position` -- specifically:

- `Var { pos, .. }` -- the position of the identifier.
- `Unary { pos, .. }` -- the position of the operator (`-` or `not`).
- `Binary { pos, .. }` -- the position of the operator token.
- `Call { pos, .. }` -- the position of the function name identifier.

Plain literals (`Expr::Int`, `Expr::Float`, `Expr::Str`, `Expr::Bool`)
carry no position -- evaluating a literal can never fail, so there is
never an error to point at.

### Values and the numeric tower

`Value` has four variants: `Int(i64)`, `Float(f64)`, `Str(String)`,
`Bool(bool)`. There is no implicit conversion between the `Str`/`Bool`
family and numbers anywhere.

**Unary operators:**

| Expression | Rule |
|---|---|
| `-x` | `x: Int` -> `Int` (negated). `x: Float` -> `Float` (negated). Negating `i64::MIN` overflows -> `EvalError::IntegerOverflow` at the `-`'s position. Anything else -> `TypeMismatch { expected: "number", found: x.type_name(), pos }`. |
| `not x` | `x: Bool` -> `Bool` (negated). Anything else -> `TypeMismatch { expected: "bool", found: x.type_name(), pos }`. |

**Binary arithmetic (`+ - *`):** evaluate the left operand, then (if left
didn't error) the right. If both are `Int`, the result is `Int` computed
with *checked* arithmetic (`checked_add`/`checked_sub`/`checked_mul`); on
overflow, `EvalError::IntegerOverflow` at the operator's position. If
either operand is `Float` (and the other is `Int` or `Float`), both are
promoted to `f64` and the result is `Float`. If either operand is `Str` or
`Bool`, that's `TypeMismatch { expected: "number", found: <that
operand's type_name()>, pos }` -- check the left operand first; only
report the right operand's type if the left one *was* a valid number.

**Division (`/`):** both operands must be numbers (same left-then-right
type check as above, same `expected: "number"`). Division **always**
promotes to `f64` and produces a `Float` result, even for two `Int`
operands (`6 / 4` is `Float(1.5)`, not integer division). Before
dividing, if the (numeric) divisor equals zero -- `Int(0)`, `Float(0.0)`,
or `Float(-0.0)` all count -- the result is `EvalError::DivisionByZero` at
the operator's position, checked *before* any type promotion of the
numerator matters.

**Comparisons (`== != < <= > >=`):** both operands are always evaluated
(left then right; first error wins). Values belong to one of three
*families*: `number` (`Int` or `Float`), `string` (`Str`), `bool`
(`Bool`).

- `==`/`!=`: valid within any single family.
  - Two numbers: if both are `Int`, compared exactly as `i64`; otherwise
    both promoted to `f64` and compared as `f64`.
  - Two strings: ordinary `String` equality.
  - Two bools: ordinary `bool` equality.
  - Cross-family (e.g. `Int` vs `Str`) -> `TypeMismatch { expected: "same
    type", found: <right operand's type_name()>, pos }`.
- `< <= > >=`: valid only for two numbers (same promotion rule as above)
  or two strings (ordinary lexicographic `String`/`str` ordering,
  i.e. `Ord` on `str`). Bools have no ordering.
  - Cross-family -> `TypeMismatch { expected: "same type", found: <right
    operand's type_name()>, pos }`.
  - Same family but both `Bool` -> `TypeMismatch { expected: "number or
    string", found: "bool", pos }`.

**`and` / `or` (short-circuit, both operands must be `Bool`):**

- `a and b`: evaluate `a`. If `a` is not `Bool`, `TypeMismatch { expected:
  "bool", found: a.type_name(), pos }` (operator's position) -- `b` is
  *not evaluated*. If `a` is `Bool(false)`, the result is `Bool(false)`
  and **`b` is never evaluated** (no type check on `b`, no error even if
  `b` would itself divide by zero or reference an unknown variable). If
  `a` is `Bool(true)`, evaluate `b`; it must be `Bool` (same error shape,
  same position) and the result is `b`'s value.
- `a or b`: symmetric -- `a` must be `Bool`; if `Bool(true)`, result is
  `Bool(true)` and `b` is never evaluated; if `Bool(false)`, evaluate `b`
  (must be `Bool`) and the result is `b`'s value.

### Variables

`Expr::Var { name, pos }` looks `name` up in the supplied `Env` (a
`HashMap<String, Value>`, cloned on lookup). Not found ->
`EvalError::UnknownVariable { name: name.clone(), pos }`.

### Built-in functions

Exactly three names are recognized at evaluation time (the parser accepts
*any* `ident(args)` call syntactically -- recognizing the name is an
`eval`-time concern, not a parse error):

- **`min(a, b)`**, **`max(a, b)`** -- both arguments must be numbers
  (`Int` or `Float`, `EvalError::TypeMismatch { expected: "number",
  found: <arg's type_name()>, pos }` at the *call's* position if not,
  arguments evaluated left to right, first error wins). Comparison for
  ordering: if both arguments are `Int`, compare exactly as `i64`;
  otherwise promote both to `f64`. The result is the *original* `Value` of
  whichever argument wins (its original `Int`/`Float` type is preserved,
  not coerced) -- `min(3, 5.5)` is `Int(3)`, not `Float(3.0)`. On a tie,
  return the **first** argument's value.
- **`round(x)`** -- `x` must be a number. `x: Int` is returned unchanged.
  `x: Float` is rounded to the nearest integer with Rust's own
  `f64::round()` tie-breaking (ties round away from zero: `2.5` ->
  `3`, `-2.5` -> `-3`) and returned as `Value::Int`. If the rounded value
  is outside the range representable by `i64`, that's
  `EvalError::IntegerOverflow` at the call's position.
- Any other name called as a function -> `EvalError::UnknownFunction {
  name: name.clone(), pos }` -- checked *before* argument count or
  argument evaluation.
- Wrong argument count for a recognized builtin (`min`/`max` need exactly
  2, `round` needs exactly 1) -> `EvalError::WrongArgCount { name,
  expected, found, pos }` (`pos` is the call's position) -- checked after
  the name is recognized, before any argument is evaluated.

Evaluation order for a call: (1) resolve the name -- `UnknownFunction` if
unrecognized; (2) check argument count -- `WrongArgCount`; (3) evaluate
arguments left to right, first error wins; (4) type-check the evaluated
values; (5) compute the result.

### `type_name()`

`Value` has an inherent method `type_name(&self) -> &'static str`
returning exactly one of `"int"`, `"float"`, `"string"`, `"bool"` --
these four literals are the only values ever placed in an `EvalError`'s
`found` field.

### Parse errors

| Variant | When |
|---|---|
| `UnexpectedChar { ch, pos }` | A character that starts no valid token (e.g. `@`, `#`, a lone `!` or `=` not part of `!=`/`==`), or an invalid escape sequence inside a string literal (`ch` is the character after the backslash, `pos` is the backslash's position). |
| `UnterminatedString { pos }` | A `"` with no matching closing `"` before the input ends. `pos` is the *opening* quote's position. |
| `InvalidNumber { text, pos }` | A numeric literal whose text doesn't fit the value type it lexes as (in practice: an integer literal too large for `i64`). `text` is the literal's exact source text, `pos` is its start. |
| `UnexpectedToken { expected, found, pos }` | A structural expectation wasn't met while parsing. `expected` is exactly one of `"expression"`, `")"`, `", or )"`. `found` is the exact source text of the token that was actually present, or the literal string `"<eof>"` if input ended instead. `pos` is that token's position (or `source.len()` for `<eof>`). |
| `TrailingInput { pos }` | A complete expression was parsed but tokens remain before EOF. `pos` is the position of the first leftover token. |

`UnexpectedToken` is what covers "unbalanced parens" in both directions:
an unclosed `(` surfaces as `UnexpectedToken { expected: ")", found:
"<eof>", .. }` (or `found` naming whatever wrong token comes next, if the
input continues but never supplies the `)`); an *extra*, unmatched `)`
surfaces as `TrailingInput` once the outer expression is already complete.

### A worked example

`"(price * 1.15) - (has_coupon and 5 or 0)"` with an `Env` containing
`price -> Float(20.0)` and `has_coupon -> Bool(true)`:

1. `price * 1.15` -> `price` is `Float(20.0)`; `Float * Float` ->
   `Float(23.0)`.
2. `has_coupon and 5 or 0`: `has_coupon` is `Bool(true)`, so evaluate the
   right side of `and`, which is `5` -- **not a `Bool`** ->
   `EvalError::TypeMismatch { expected: "bool", found: "int", pos:
   <position of "and"> }`. (This is intentional: this language has no
   Python-style truthy-`5`-as-a-value trick. If your rule needs "5 or 0
   depending on a flag", write it as `if`-shaped logic isn't available
   either -- this toy language doesn't have a conditional expression, only
   the operators listed above. A real rule author would instead write
   something the type system accepts, e.g. compare first:
   `has_coupon == true`.)

This example is deliberately left as a *documented error case*, not a
success case -- it's exercised directly in `tests/errors.rs` to prove
`and`/`or` never silently coerce a number to a boolean.

## Completion criteria

```bash
cargo test -p t02-toy-expression-interpreter
```

All given tests pass. There is no separate validator script -- per this
module's documented exception to the repo-wide convention (see the module
README), `cargo test` exiting non-zero on a failing/panicking assertion
*is* the "NOT PASSED" signal, and every assertion in `tests/` carries a
message explaining what should hold.

The test suite includes:

- Table-driven precedence/associativity/nesting/unary-minus cases,
  checked by evaluating full expressions against expected `Value`s.
- Numeric-tower cases: int/int stays int, any float promotes, division
  always promotes, division-by-zero and overflow are caught.
- Comparison and boolean cases, including the `and`/`or` short-circuit
  behavior (an error on the side that's never evaluated must *not*
  surface).
- String literal and escape handling, and variable lookup against a
  supplied `Env`.
- Builtin (`min`/`max`/`round`) cases, including type-preservation on
  `min`/`max` and rounding tie-breaking.
- An explicit error battery asserting the exact variant *and* the exact
  `Position` for every error case in this README -- not just "it
  returned `Err(..)`".
- A handful of fixed expressions checked against their exact expected
  `Expr` tree (structural/round-trip tests) -- this catches a shortcut
  evaluator that computes an answer without ever building a real AST.
- Property-style tests that build random well-formed expression trees
  with `sandbox18_harness::prng::Xorshift64` (a fixed seed, so failures
  are reproducible), render them to source text, and independently
  compute the expected value straight from the generated tree (not by
  calling anything in this crate) -- so memorizing fixed test inputs
  cannot pass this part of the suite.

## Estimated evenings

2

## Topics to read up on

- Recursive-descent parsing and precedence climbing (why each grammar
  tier calling the next-tighter tier is what encodes operator precedence,
  without a separate precedence table)
- Tokenizing with lifetimes: why a `Token<'a>` borrowing from the input
  `&str` avoids allocating a `String` per token, and what that borrow
  implies about how long the token stream can live relative to the source
- `Box<T>` for recursive enum variants, and why an enum containing itself
  directly (without indirection) can't have a known size at compile time
- Exhaustive `match` and how it turns "I added an AST variant" into a
  compiler-enforced checklist of every place that needs updating
- `Result` and the `?` operator for threading errors up through nested
  recursive calls, plus `From` conversions for combining two error types
  into one
- Numeric promotion / a "numeric tower" as a language-design concept
  distinct from Rust's own (stricter) numeric type rules -- this task's
  promotion rules are the *interpreted language's* semantics, not Rust's
- Short-circuit boolean evaluation and why it's observable (which
  side-effects -- here, which errors -- never happen) rather than just a
  performance detail

## Off-limits

`.authoring/design.md` (at the module root) documents this task's
grading philosophy and anti-cheat rationale -- spoilers. Don't read it
before finishing this task.
