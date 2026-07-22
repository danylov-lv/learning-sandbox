//! Applies `#[derive(Builder)]` to a local struct and asserts on the
//! generated BEHAVIOR (values produced, method chaining) -- never on the
//! generated source text. A macro that emits nothing fails this file at
//! compile time already (`Person::builder()` / `PersonBuilder` wouldn't
//! exist); a macro that emits a hardcoded/default struct regardless of what
//! was set fails the equality assertions below, since every value used here
//! is deliberately non-default.

use t09_proc_macro_bonus::Builder;

#[derive(Builder, Debug, PartialEq, Eq)]
struct Person {
    name: String,
    age: u32,
    nickname: Option<String>,
}

#[test]
fn all_fields_set_via_chained_setters_build_the_expected_struct() {
    let person = Person::builder()
        .name("Ada Lovelace".to_string())
        .age(36)
        .nickname("Ada".to_string())
        .build()
        .expect("every required field was set, and the optional field was also set, so build() must succeed");

    assert_eq!(
        person,
        Person {
            name: "Ada Lovelace".to_string(),
            age: 36,
            nickname: Some("Ada".to_string()),
        },
        "build() must return a struct carrying exactly the values passed to each setter, not a \
         default/hardcoded Person -- got {person:?}"
    );
}

#[test]
fn setters_can_be_called_in_any_order() {
    // Same values as the test above, called in a different order. If the
    // generated setters didn't each return `Self` (i.e. weren't chainable),
    // or if the builder secretly depended on call order, this would either
    // fail to compile or produce a different struct than the equivalent
    // forward-order call.
    let person = Person::builder()
        .nickname("Ada".to_string())
        .age(36)
        .name("Ada Lovelace".to_string())
        .build()
        .expect("order of setter calls must not matter for a correctly-built builder");

    assert_eq!(
        person,
        Person {
            name: "Ada Lovelace".to_string(),
            age: 36,
            nickname: Some("Ada".to_string()),
        },
        "calling the same three setters in reverse order must build the same Person, got {person:?}"
    );
}

#[test]
fn omitting_only_the_optional_field_still_succeeds_with_none() {
    let person = Person::builder()
        .name("Grace Hopper".to_string())
        .age(85)
        .build()
        .expect("nickname is Option<String>, so build() must succeed without it ever being set");

    assert_eq!(
        person,
        Person {
            name: "Grace Hopper".to_string(),
            age: 85,
            nickname: None,
        },
        "an untouched Option<T> field must default to None in the built struct, got {person:?}"
    );
}

#[test]
fn calling_a_setter_twice_keeps_the_last_value() {
    let person = Person::builder()
        .name("First Name".to_string())
        .name("Second Name".to_string())
        .age(1)
        .build()
        .expect("all required fields were set at least once");

    assert_eq!(
        person.name, "Second Name",
        "calling the same setter twice must overwrite the previous value, not accumulate or \
         keep the first one -- got {:?}",
        person.name
    );
}
