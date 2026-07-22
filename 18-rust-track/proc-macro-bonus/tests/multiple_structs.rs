//! Proves the derive is genuinely generic -- driven by each struct's own
//! name and field list, not hardcoded for a single shape -- by applying it
//! to three different structs in the same crate: different struct names
//! (so `<Struct>Builder` naming can't collide or be hardcoded), different
//! field counts and types (so field handling isn't specialized to
//! `String`/`u32`), and one struct that is entirely optional fields (so the
//! "no required fields" edge case is exercised).

use t09_proc_macro_bonus::Builder;

#[derive(Builder, Debug, PartialEq)]
struct Rectangle {
    width: f64,
    height: f64,
    label: Option<String>,
}

#[derive(Builder, Debug, PartialEq, Eq)]
struct Flags {
    verbose: bool,
    retries: i64,
}

#[derive(Builder, Debug, PartialEq, Eq)]
struct AllOptional {
    a: Option<u32>,
    b: Option<String>,
}

#[test]
fn a_second_struct_gets_its_own_correctly_named_builder_and_real_values() {
    let rect = Rectangle::builder()
        .width(3.5)
        .height(2.0)
        .label("box".to_string())
        .build()
        .expect("both required fields (width, height) were set");

    assert_eq!(
        rect,
        Rectangle {
            width: 3.5,
            height: 2.0,
            label: Some("box".to_string()),
        },
        "RectangleBuilder must produce a Rectangle carrying the exact values set, got {rect:?}"
    );
    assert_eq!(
        rect.width * rect.height,
        7.0,
        "sanity check on the actual f64 values stored, not just that *a* struct came back"
    );
}

#[test]
fn a_third_struct_with_different_field_types_builds_and_reports_missing_fields() {
    let flags = Flags::builder()
        .verbose(true)
        .retries(5)
        .build()
        .expect("both required fields were set");
    assert_eq!(
        flags,
        Flags {
            verbose: true,
            retries: 5,
        },
        "bool and i64 fields must round-trip through the builder untouched, got {flags:?}"
    );

    let err = Flags::builder()
        .verbose(false)
        .build()
        .expect_err("`retries` was never set");
    assert_eq!(
        err, "missing required field(s): retries",
        "Flags has no Option fields, so the only ever-missing field here is `retries`"
    );
}

#[test]
fn a_struct_with_only_optional_fields_builds_with_no_setters_called_at_all() {
    let built = AllOptional::builder()
        .build()
        .expect("every field is Option<T>, so there are no required fields to be missing");

    assert_eq!(
        built,
        AllOptional { a: None, b: None },
        "with zero setters called, every Option field must default to None, got {built:?}"
    );
}

#[test]
fn a_struct_with_only_optional_fields_still_accepts_values_when_set() {
    let built = AllOptional::builder()
        .a(7)
        .b("seven".to_string())
        .build()
        .expect("build() on an all-optional struct always succeeds");

    assert_eq!(
        built,
        AllOptional {
            a: Some(7),
            b: Some("seven".to_string()),
        },
        "setters on optional fields must still take effect when called, got {built:?}"
    );
}
