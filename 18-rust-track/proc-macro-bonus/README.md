# Bonus -- proc-macro-bonus (`#[derive(Builder)]`)

This task is optional. It sits outside the eight-task main sequence and
isn't required to consider the module complete -- do it if you want a look
at the one corner of Rust the other seven tasks don't touch: code that
writes code.

## Backstory

Every struct in this repo that has more than two or three fields has, at
some point, wanted a nicer construction story than a giant positional
struct literal -- optional fields you sometimes skip, a constructor that
can fail if you forgot something, values set in whatever order is
convenient at the call site rather than the order the struct happens to
declare them in. Hand-writing that builder boilerplate once is fine.
Hand-writing it for the twentieth struct is exactly the kind of repetitive,
mechanical, "the compiler could have told me this" work Rust's
`#[derive(...)]` mechanism exists to eliminate -- you've been consuming
derives like `Debug`, `Clone`, and `PartialEq` all module; this task is
where you write one instead of just using one.

A derive macro is a function that runs *during compilation* of whatever
crate uses it: it receives the annotated item as a token stream, and
returns a token stream of additional code the compiler splices in right
next to it. That's a different mental model from everything else in this
module -- there's no runtime here to step through, no data to print;
the "input" is source code and the "output" is more source code, and the
only way to know it's right is to compile something that uses it and
watch what that something does.

## What's given

- `src/lib.rs` -- a scaffold. The `#[proc_macro_derive(Builder)]` entry
  function is fully declared: parsing the input via
  `syn::parse_macro_input!`, matching on `Data::Struct` with
  `Fields::Named`, and the compile-error path for anything else (an enum,
  a union, a tuple struct, a unit struct) via `syn::Error::to_compile_error`
  are all given, not part of the exercise. The actual code generation --
  everything from "decide which fields are required vs optional" through
  emitting the builder struct, its setters, and `build()` with `quote!` --
  is a single `todo!()`. You write all of that; the shape (what's parsed,
  what's rejected, what the function returns) is fixed.
- `tests/` -- the validator, three files, all given. They `#[derive(Builder)]`
  on structs declared right there in the test file and assert on values
  the generated code produces -- never on the generated code's source
  text. Read them before you start; they are, in aggregate, a more precise
  specification of the contract below than the prose is.
- This README's "Generated-code contract" section: the *only* place the
  exact shape of what you must generate is written down. If your instinct
  disagrees with it, the README wins, because that's what the tests were
  written against.

## What's required

Implement the body of `derive_builder` in `src/lib.rs`: given the fields of
a struct with named fields (already extracted for you as a
`syn::punctuated::Punctuated<syn::Field, syn::Token![,]>`), use `quote!` to
generate the builder struct, its setters, and `build()`, exactly as
specified below, and return that as a `proc_macro::TokenStream`.

## Generated-code contract

Given:

```rust
#[derive(Builder)]
struct Person {
    name: String,
    age: u32,
    nickname: Option<String>,
}
```

`#[derive(Builder)]` must generate code equivalent to:

```rust
pub struct PersonBuilder {
    name: Option<String>,
    age: Option<u32>,
    nickname: Option<String>,
}

impl Person {
    pub fn builder() -> PersonBuilder {
        PersonBuilder { name: None, age: None, nickname: None }
    }
}

impl PersonBuilder {
    pub fn name(mut self, value: String) -> Self {
        self.name = Some(value);
        self
    }
    pub fn age(mut self, value: u32) -> Self {
        self.age = Some(value);
        self
    }
    pub fn nickname(mut self, value: String) -> Self {
        self.nickname = Some(value);
        self
    }

    pub fn build(self) -> Result<Person, String> {
        let mut missing: Vec<&str> = Vec::new();
        if self.name.is_none() { missing.push("name"); }
        if self.age.is_none() { missing.push("age"); }
        if !missing.is_empty() {
            return Err(format!("missing required field(s): {}", missing.join(", ")));
        }
        Ok(Person {
            name: self.name.unwrap(),
            age: self.age.unwrap(),
            nickname: self.nickname,
        })
    }
}
```

Point by point:

1. **Builder type name.** For a struct `Foo`, generate `pub struct
   FooBuilder` -- exactly `{StructName}Builder`, no other naming scheme.
   `impl Foo { pub fn builder() -> FooBuilder }` is the one entry point;
   there is no `FooBuilder::new()`.
2. **Required vs optional fields.** A field is **optional** if its
   declared type is *literally* `Option<Inner>` written that way in the
   source (a bare `Option` path segment with one angle-bracketed type
   argument) -- everything else is **required**. You are not required to
   recognize a fully-qualified `std::option::Option<T>` or
   `core::option::Option<T>`; none of the given tests use that spelling.
3. **Builder fields.** Every field, required or optional, is stored in the
   builder as `Option<StoredTy>`, where `StoredTy` is the field's own
   declared type for a required field, or the *unwrapped inner type* for
   an optional one (so an optional `nickname: Option<String>` becomes a
   builder field `nickname: Option<String>` too -- not
   `Option<Option<String>>`). All start as `None`.
4. **Setters.** One per field, named after the field, taking `StoredTy` by
   value, returning `Self` so calls chain:
   `pub fn <field>(mut self, value: StoredTy) -> Self`. For an optional
   field this means the setter takes the *unwrapped* value (`String`, not
   `Option<String>`) -- callers never write `Some(...)` themselves.
   Setters may be called in any order, any number of times (last call
   wins), and calling only some of them is always allowed.
5. **`build(self) -> Result<Struct, String>`.**
   - Collect the names of every **required** field that is still `None`,
     in the order the fields are declared in the struct. Optional fields
     are never added to this list, whether they were set or not.
   - If that list is non-empty, return
     `Err(format!("missing required field(s): {}", <names joined with ", ">))`
     -- this exact format, comma-and-space-separated, declaration order.
     A struct with zero required fields therefore can never produce this
     `Err` at all.
   - Otherwise, return `Ok(Struct { ... })`: unwrap every required field
     (safe -- just confirmed present), and pass every optional field's
     `Option<Inner>` straight through unchanged (`None` if never set).

Nothing else is part of the contract: no per-field attributes, no default
values other than `None` for unset optional fields, no validation beyond
"was this required field set at all."

## Completion criteria

```bash
cd 18-rust-track
cargo test -p t09-proc-macro-bonus
```

All given tests pass. They cover, at minimum:

- All fields set through chained setters, in both declaration order and a
  different order, build the exact expected struct.
- An unset `Option<T>` field defaults to `None` in the built struct.
- Calling the same setter twice keeps the later value.
- One missing required field is named exactly, alone, in the error.
- Two missing required fields are both named, in declaration order, in a
  single error -- not just the first one found.
- Setting only the optional field never counts toward satisfying the
  required fields.
- A second and third struct, with different names, different field
  counts, and different field types (`f64`, `bool`, `i64`, not just
  `String`/`u32`), each get their own correctly-named, independently
  working builder -- proving the derive is driven by the annotated
  struct's actual shape, not hardcoded against one example.
- A struct with *only* optional fields builds successfully with zero
  setters called at all.

### A note on how the stub fails

Before you implement anything, `cargo test -p t09-proc-macro-bonus` does
not fail the way a normal `todo!()` does elsewhere in this module. A
derive macro's body runs *during compilation of whatever crate uses it* --
so the `todo!()` panics while the **test crate** is being compiled, and
that panic is reported by `rustc` as a compile error (`error: proc-macro
derive panicked`, with your `todo!()` message attached as a `help:` note)
rather than as a failing test. `cargo test` still exits non-zero either
way -- this is expected and is exactly what "the stub fails cleanly"
means for a proc-macro crate.

## Estimated evenings

1

## Topics to read up on

- What a derive macro actually is: a function from `TokenStream` to
  `TokenStream` that runs at compile time, and why that makes it a
  fundamentally different kind of code to write and debug than everything
  else in this module
- `syn::DeriveInput` / `syn::Data` / `syn::Fields` -- the parsed shape of
  "a Rust item that has a derive attribute on it," and why matching on
  `Fields::Named` (rather than assuming every struct looks like this) is
  what makes the compile-error path for tuple/unit structs possible
- `quote!`'s `#variable` interpolation and `#(#iterator),*` repetition --
  how a `Vec` of tokens becomes a comma-separated sequence of generated
  items without you hand-writing a loop that pushes strings
- Why the generated code is spliced in as *sibling* items (a new struct,
  a new `impl` block) rather than modifying the original struct in place
  -- a derive macro can only ever *add* code, never rewrite the item it's
  attached to
- `syn::Type` as a matchable enum (`Type::Path`, among many others) and
  why detecting "is this literally `Option<T>`" requires walking the
  parsed type's path segments rather than comparing strings
- The difference between a `proc-macro2::TokenStream` (a library-friendly,
  testable token stream `syn`/`quote` operate on) and a
  `proc_macro::TokenStream` (the compiler-only type the crate's public
  function must actually receive and return)
- Why `trybuild`-style "does this fail to compile" testing exists as a
  whole separate crate in the ecosystem, and why this task deliberately
  avoids needing it (every test here compiles successfully and asserts on
  runtime values instead)

## Off-limits

`.authoring/design.md` (at the module root) documents this task's grading
philosophy and anti-cheat rationale -- spoilers. Don't read it before
finishing this task.
