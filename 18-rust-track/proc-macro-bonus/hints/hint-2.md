## Detecting `Option<Inner>`

`fields` (what the scaffold hands you) is a
`syn::punctuated::Punctuated<syn::Field, syn::Token![,]>` -- iterate it
with `.iter()`, giving you `&syn::Field` per field. `field.ident` is an
`Option<syn::Ident>` (always `Some` for a named field -- you already
matched on `Fields::Named` to get here) and `field.ty` is a `syn::Type`.

To check "is this type `Option<Inner>`":

1. Match `&field.ty` against `syn::Type::Path(type_path)`. Anything else
   (a reference, a tuple, an array, ...) is definitely not `Option<_>`.
2. Look at `type_path.path.segments.last()` -- the *last* segment, so that
   both `Option<T>` and (if you wanted to support it, though you don't
   need to) `std::option::Option<T>` share this same first check.
3. Compare that segment's `.ident` against `"Option"` (`segment.ident ==
   "Option"` works directly -- `syn::Ident` implements `PartialEq<str>`).
4. If it matches, look at `segment.arguments`, a `syn::PathArguments`.
   You want the `PathArguments::AngleBracketed(args)` case; `args.args` is
   a `Punctuated<GenericArgument, Comma>` -- pull the first
   `GenericArgument::Type(inner_ty)` out of it. That `inner_ty` (a
   `&syn::Type`) is your `Inner`.

Write this as one small function, `fn option_inner(ty: &syn::Type) ->
Option<&syn::Type>`, returning `None` for "not an `Option`" and `Some(inner)`
otherwise. Every other piece of per-field logic (deciding `StoredTy`,
whether it's required) reads off this one function's result.

## Building the per-field pieces

For each field, once you know `ident` and (`stored_ty`, `is_optional`),
build up several parallel iterators/`Vec`s -- one per *kind* of generated
snippet you'll need repeated across fields:

- builder struct field defs: `quote! { #ident: Option<#stored_ty> }`
- builder field initializers (for `builder()`): `quote! { #ident: None }`
- setters: `quote! { pub fn #ident(mut self, value: #stored_ty) -> Self { self.#ident = Some(value); self } }`
- for `build()`: a per-*required*-field missing check
  (`quote! { if self.#ident.is_none() { missing.push(#name_str_lit); } }`,
  where `#name_str_lit` needs to be a `syn::LitStr`, not the bare
  identifier -- `syn::LitStr::new(&ident.to_string(), ident.span())` turns
  an `Ident` into a string literal `quote!` can splice as `"field_name"`)
- for `build()`'s final struct literal: `#ident: self.#ident.unwrap()` for
  required, `#ident: self.#ident` (no unwrap -- it's already the right
  `Option<Inner>` shape) for optional

## Assembling everything

`quote!`'s repetition syntax, `#(#some_iterator),*`, takes anything
implementing `IntoIterator` over something `quote!`-splicable (a
`TokenStream`, or anything implementing `quote::ToTokens`) and repeats the
template once per item, joined by whatever's between the `*` and the
closing `#(...)`  -- here, a comma. Build one `Vec<proc_macro2::TokenStream>`
(or keep them as iterators, `quote!` accepts either) per bullet above, then
splice all of them into one big `quote! { ... }` producing the struct def,
the two `impl` blocks, and the `build()` body's missing-field loop plus
final `Ok(...)` construction. The whole thing gets `.into()`'d at the end
to convert the `proc_macro2::TokenStream` `quote!` produces into the
`proc_macro::TokenStream` your function must return.

Watch one lifetime wrinkle: if you build a small local `struct FieldInfo`
to carry `(ident, stored_ty, is_optional)` per field so you're not
recomputing `option_inner` three times, borrow `ident` from the original
`syn::Field` (`&'a syn::Ident`) rather than cloning it -- `quote!` happily
splices a borrowed `&syn::Ident` the same as an owned one.
