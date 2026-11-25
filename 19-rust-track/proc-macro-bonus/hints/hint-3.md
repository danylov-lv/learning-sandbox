Prose sketches close to pseudocode. You still have to write and debug the
actual Rust -- nothing here is copy-pasteable, and none of it compiles as
written.

## `option_inner`

```
fn option_inner(ty: &Type) -> Option<&Type> {
    let Type::Path(type_path) = ty else { return None; };
    let segment = type_path.path.segments.last()?;
    if segment.ident != "Option" { return None; }
    let PathArguments::AngleBracketed(args) = &segment.arguments else { return None; };
    args.args.iter().find_map(|arg| match arg {
        GenericArgument::Type(inner) => Some(inner),
        _ => None,
    })
}
```

## Per-field info

```
struct FieldInfo<'a> {
    ident: &'a syn::Ident,
    stored_ty: proc_macro2::TokenStream,  // the field's own Ty, or Option's Inner
    is_optional: bool,
}

let infos: Vec<FieldInfo> = fields.iter().map(|f| {
    let ident = f.ident.as_ref().unwrap();
    match option_inner(&f.ty) {
        Some(inner) => FieldInfo { ident, stored_ty: quote!(#inner), is_optional: true },
        None => { let ty = &f.ty; FieldInfo { ident, stored_ty: quote!(#ty), is_optional: false } }
    }
}).collect();
```

## The four families of per-field tokens

```
let builder_field_defs  = infos.iter().map(|i| { let (id, ty) = (i.ident, &i.stored_ty);
    quote! { #id: Option<#ty> } });
let builder_field_inits = infos.iter().map(|i| { let id = i.ident; quote! { #id: None } });
let setters = infos.iter().map(|i| { let (id, ty) = (i.ident, &i.stored_ty);
    quote! { pub fn #id(mut self, value: #ty) -> Self { self.#id = Some(value); self } } });
let build_fields = infos.iter().map(|i| { let id = i.ident;
    if i.is_optional { quote! { #id: self.#id } } else { quote! { #id: self.#id.unwrap() } } });
```

## Missing-field checks (required fields only)

```
let required: Vec<&FieldInfo> = infos.iter().filter(|i| !i.is_optional).collect();
let missing_checks = required.iter().map(|i| {
    let id = i.ident;
    let name_lit = syn::LitStr::new(&id.to_string(), id.span());
    quote! { if self.#id.is_none() { missing.push(#name_lit); } }
});
```

## Final assembly

```
let expanded = quote! {
    pub struct #builder_name {
        #(#builder_field_defs),*
    }

    impl #struct_name {
        pub fn builder() -> #builder_name {
            #builder_name { #(#builder_field_inits),* }
        }
    }

    impl #builder_name {
        #(#setters)*

        pub fn build(self) -> Result<#struct_name, String> {
            let mut missing: Vec<&str> = Vec::new();
            #(#missing_checks)*
            if !missing.is_empty() {
                return Err(format!("missing required field(s): {}", missing.join(", ")));
            }
            Ok(#struct_name { #(#build_fields),* })
        }
    }
};

expanded.into()
```

One gotcha worth knowing before you hit it yourself: each of
`builder_field_defs`, `setters`, etc. is an iterator (from `.map(...)`),
and `quote!`'s `#(...)* ` repetition consumes an iterator by value. If you
try to use the *same* iterator variable inside two different `quote!{...}`
blocks, or read `infos` in two separate `.map()` calls that both try to
move out of it, the borrow checker will stop you before the macro logic
even gets a chance to be wrong -- build each family of tokens (the
`Vec`/iterator for defs, inits, setters, missing-checks, build-fields)
once, from `infos.iter()` (borrowing, not consuming `infos`), and reuse
each one exactly once in the final `quote!`.
