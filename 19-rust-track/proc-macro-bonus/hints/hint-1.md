Step back from `quote!` and `syn` for a second and think about what you're
actually building, in plain English, for one field: "for a required field,
the builder stores an `Option` of it, offers a setter that fills it in,
and `build()` has to check it got filled before unwrapping it; for an
optional field, everything's the same except `build()` never checks."
Everything in the codegen is that idea, repeated once per field and
stitched into three items (a struct, an inherent `impl` for the original
type, an inherent `impl` for the builder). If you can write that sentence
for a specific, concrete struct by hand -- literally type out the
`PersonBuilder` from this README's contract yourself, no macro involved --
you already know everything the macro needs to produce; the rest is
"which parts of what I just wrote change per-field, per-struct, and how do
I get `syn` to hand me those parts."

The one genuinely new piece of information you need before writing any
code is: how do you tell, from a `syn::Field`, whether its type is
`Option<something>`? `syn` gives you the field's type as a `syn::Type`,
which is an enum -- and `Option<String>` parses as a `Type::Path` whose
last path segment is the identifier `Option` carrying one angle-bracketed
generic type argument. That's a structural check, not a string comparison
-- go read `syn::Type`, `syn::PathArguments`, and `syn::GenericArgument`'s
docs before you write the detection function; guessing the shape from
memory is the slow way to do this.

Everything else -- building the actual output tokens -- is `quote!` used
exactly the way you've already seen it used in every derive macro's
example code you've ever skimmed past: `#some_variable` splices a value
in, `#(#some_iterator),*` repeats a template once per item in something
iterable, comma-separated. You do not need any `quote!` feature beyond
those two.
