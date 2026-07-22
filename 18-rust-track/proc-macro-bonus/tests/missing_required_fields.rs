//! Locks down the exact `build()` error contract for missing required
//! fields (see README.md's "Generated-code contract"): a `String` reading
//! `"missing required field(s): "` followed by every unset required
//! field's name, comma-and-space separated, in the order the fields are
//! declared in the struct -- optional (`Option<T>`) fields never appear in
//! that list, set or not.
//!
//! A macro that ignores missing fields and always returns `Ok` fails every
//! test here; one that reports only the first missing field (instead of
//! all of them) fails `two_missing_required_fields_are_both_named`.

use t09_proc_macro_bonus::Builder;

#[derive(Builder, Debug, PartialEq, Eq)]
struct Person {
    name: String,
    age: u32,
    nickname: Option<String>,
}

#[test]
fn one_missing_required_field_is_named_exactly() {
    let err = Person::builder()
        .age(30)
        .build()
        .expect_err("`name` was never set, so build() must return Err, not Ok");

    assert_eq!(
        err, "missing required field(s): name",
        "the error must name exactly the one unset required field, `name`, and nothing else"
    );
}

#[test]
fn a_different_single_missing_field_is_named_exactly() {
    let err = Person::builder()
        .name("Alan Turing".to_string())
        .build()
        .expect_err("`age` was never set, so build() must return Err, not Ok");

    assert_eq!(
        err, "missing required field(s): age",
        "the error must name exactly the one unset required field, `age`, not `name` (which \
         WAS set) and not the optional `nickname`"
    );
}

#[test]
fn two_missing_required_fields_are_both_named_in_declaration_order() {
    // Neither `name` nor `age` was set; `nickname` (optional) was not
    // touched either but must never appear in the error.
    let err = Person::builder()
        .build()
        .expect_err("neither required field was set, so build() must return Err");

    assert_eq!(
        err, "missing required field(s): name, age",
        "both missing required fields must be listed, in the order they're declared in the \
         struct (name before age) -- a builder that bails after the first missing field would \
         report only \"missing required field(s): name\" here"
    );
}

#[test]
fn setting_the_optional_field_alone_does_not_satisfy_required_fields() {
    let err = Person::builder()
        .nickname("Al".to_string())
        .build()
        .expect_err("setting only the optional field leaves both required fields unset");

    assert_eq!(
        err, "missing required field(s): name, age",
        "an optional field being set must not be mistaken for a required field being set -- \
         `name` and `age` are still both missing"
    );
}
