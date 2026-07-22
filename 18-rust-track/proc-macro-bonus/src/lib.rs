//! t09-proc-macro-bonus (optional).
//!
//! `#[derive(Builder)]`: given a struct with named fields, generates a
//! `<Struct>Builder` type with a chained setter per field and a
//! `build(self) -> Result<Struct, String>`. See README.md for the exact
//! generated-code contract (setter signatures, which fields count as
//! "required" vs "optional", the exact missing-field error shape) --
//! `tests/` applies this derive to local structs and is the validator.

use proc_macro::TokenStream;
use quote::{format_ident, quote};
use syn::{parse_macro_input, Data, DeriveInput, Fields};

#[proc_macro_derive(Builder)]
pub fn derive_builder(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as DeriveInput);

    // Only structs with named fields are supported. Anything else (an enum,
    // a union, a tuple struct, a unit struct) is a compile-time error at the
    // derive site, not a panic -- this part is given, not part of the
    // exercise.
    let fields = match &input.data {
        Data::Struct(data) => match &data.fields {
            Fields::Named(fields) => &fields.named,
            _ => {
                return syn::Error::new_spanned(
                    &input.ident,
                    "Builder can only be derived for structs with named fields",
                )
                .to_compile_error()
                .into();
            }
        },
        _ => {
            return syn::Error::new_spanned(
                &input.ident,
                "Builder can only be derived for structs, not enums or unions",
            )
            .to_compile_error()
            .into();
        }
    };

    let struct_name = &input.ident;
    let builder_name = format_ident!("{}Builder", struct_name);
    let field_count = fields.len();

    // TODO(learner): this is the actual exercise. Using `fields` (a
    // `syn::punctuated::Punctuated<syn::Field, syn::Token![,]>`), build the
    // token stream for:
    //
    //   pub struct #builder_name { <field>: Option<StoredTy>, ... }
    //
    //   impl #struct_name {
    //       pub fn builder() -> #builder_name { ... every field: None ... }
    //   }
    //
    //   impl #builder_name {
    //       // one setter per field, chainable:
    //       pub fn <field>(mut self, value: StoredTy) -> Self {
    //           self.<field> = Some(value);
    //           self
    //       }
    //
    //       pub fn build(self) -> Result<#struct_name, String> {
    //           // collect the names of every REQUIRED field that is still
    //           // None, in declaration order; if that list isn't empty,
    //           // return Err(format!("missing required field(s): {}", ...));
    //           // otherwise construct #struct_name, unwrapping required
    //           // fields and passing optional fields' Option through as-is.
    //       }
    //   }
    //
    // For a field `name: Ty`, StoredTy is `Ty` itself UNLESS `Ty` is
    // literally `Option<Inner>`, in which case that field is OPTIONAL:
    // StoredTy is `Inner` (the setter takes the unwrapped value, not an
    // `Option`), and build() must not error if it was never set -- it just
    // passes `self.<field>` (already an `Option<Inner>`) straight through.
    // See README.md's "Generated-code contract" section for the full
    // worked example and the exact error-message format.
    todo!(
        "generate `{struct_name}::builder()`, `{builder_name}`'s struct definition, its \
         {field_count} setter(s), and build() with quote! -- see README.md's \
         'Generated-code contract' section for the exact shape every generated item must have"
    )
}
