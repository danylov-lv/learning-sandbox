//! Comparison operators (across the number/string/bool families) and the
//! `and`/`or` short-circuit contract: the side that's never evaluated must
//! never surface an error, even if it would otherwise divide by zero or
//! reference a missing variable.

use std::collections::HashMap;
use t02_toy_expression_interpreter::{EvalError, InterpError, Value, eval_source};

fn env() -> HashMap<String, Value> {
    HashMap::new()
}

#[test]
fn numeric_comparisons_mixed_int_float() {
    let cases: &[(&str, bool)] = &[
        ("1 < 2", true),
        ("2 < 1", false),
        ("1 <= 1", true),
        ("2 >= 3", false),
        ("3 > 2", true),
        ("1 == 1", true),
        ("1 == 1.0", true), // cross-type numeric equality via promotion
        ("1 != 2", true),
        ("2.5 < 3", true),
        ("3 < 2.5", false),
        ("2.0 == 2", true),
        ("0.1 + 0.2 != 1", true), // sanity: unrelated float doesn't equal 1
    ];
    for (source, expected) in cases {
        match eval_source(source, &env()) {
            Ok(Value::Bool(b)) => assert_eq!(
                b, *expected,
                "`{source}` should evaluate to Bool({expected})"
            ),
            other => panic!("`{source}` must evaluate to Value::Bool({expected}), got {other:?}"),
        }
    }
}

#[test]
fn string_equality_and_ordering() {
    let cases: &[(&str, bool)] = &[
        (r#""abc" == "abc""#, true),
        (r#""abc" == "abd""#, false),
        (r#""abc" != "xyz""#, true),
        (r#""abc" < "abd""#, true),
        (r#""b" > "a""#, true),
        (r#""apple" < "banana""#, true),
    ];
    for (source, expected) in cases {
        match eval_source(source, &env()) {
            Ok(Value::Bool(b)) => assert_eq!(
                b, *expected,
                "`{source}` should evaluate to Bool({expected}) under lexicographic string comparison"
            ),
            other => panic!("`{source}` must evaluate to Value::Bool({expected}), got {other:?}"),
        }
    }
}

#[test]
fn bool_equality_but_no_bool_ordering() {
    match eval_source("true == true", &env()) {
        Ok(Value::Bool(true)) => {}
        other => panic!("`true == true` must evaluate to Value::Bool(true), got {other:?}"),
    }
    match eval_source("true != false", &env()) {
        Ok(Value::Bool(true)) => {}
        other => panic!("`true != false` must evaluate to Value::Bool(true), got {other:?}"),
    }
    match eval_source("true < false", &env()) {
        Err(InterpError::Eval(EvalError::TypeMismatch { expected, found, .. })) => {
            assert_eq!(expected, "number or string", "ordering two bools must report expected == \"number or string\"");
            assert_eq!(found, "bool", "ordering two bools must report found == \"bool\"");
        }
        other => panic!("`true < false` must fail with TypeMismatch{{expected: \"number or string\", found: \"bool\"}}, got {other:?}"),
    }
}

#[test]
fn cross_family_comparison_is_a_type_mismatch() {
    match eval_source(r#"1 == "1""#, &env()) {
        Err(InterpError::Eval(EvalError::TypeMismatch { expected, found, .. })) => {
            assert_eq!(expected, "same type", "cross-family == must report expected == \"same type\"");
            assert_eq!(found, "string", "cross-family == must report the right operand's type_name (\"string\")");
        }
        other => panic!(r#"`1 == "1"` must fail with TypeMismatch{{expected: "same type", found: "string"}}, got {other:?}"#),
    }
    match eval_source("true == 1", &env()) {
        Err(InterpError::Eval(EvalError::TypeMismatch { expected, found, .. })) => {
            assert_eq!(expected, "same type");
            assert_eq!(found, "int");
        }
        other => panic!("`true == 1` must fail with TypeMismatch{{expected: \"same type\", found: \"int\"}}, got {other:?}"),
    }
}

#[test]
fn and_short_circuits_on_false_never_evaluating_the_right_side() {
    // If short-circuit weren't implemented, the right side (division by
    // zero) would surface an error here -- it must not.
    let source = "false and (1 / 0 == 0)";
    match eval_source(source, &env()) {
        Ok(Value::Bool(false)) => {}
        other => panic!(
            "`{source}` must short-circuit to Bool(false) without ever evaluating the right \
             side (which divides by zero); got {other:?}"
        ),
    }
}

#[test]
fn or_short_circuits_on_true_never_evaluating_the_right_side() {
    let source = "true or (1 / 0 == 0)";
    match eval_source(source, &env()) {
        Ok(Value::Bool(true)) => {}
        other => panic!(
            "`{source}` must short-circuit to Bool(true) without ever evaluating the right \
             side (which divides by zero); got {other:?}"
        ),
    }
}

#[test]
fn and_short_circuit_also_skips_unknown_variable_on_the_right() {
    let source = "false and this_var_does_not_exist";
    match eval_source(source, &env()) {
        Ok(Value::Bool(false)) => {}
        other => panic!(
            "`{source}` must short-circuit to Bool(false) without evaluating the right side \
             (an unknown variable); got {other:?}"
        ),
    }
}

#[test]
fn and_evaluates_right_side_when_left_is_true() {
    let source = "true and false";
    match eval_source(source, &env()) {
        Ok(Value::Bool(false)) => {}
        other => panic!("`{source}`: when left is true, right side must be evaluated and returned; got {other:?}"),
    }
}

#[test]
fn or_evaluates_right_side_when_left_is_false() {
    let source = "false or true";
    match eval_source(source, &env()) {
        Ok(Value::Bool(true)) => {}
        other => panic!("`{source}`: when left is false, right side must be evaluated and returned; got {other:?}"),
    }
}

#[test]
fn and_on_non_bool_left_is_a_type_mismatch_and_right_is_never_touched() {
    // The right side references an unknown variable; if the left-side type
    // check ran *after* evaluating the right side, this would report
    // UnknownVariable instead of TypeMismatch.
    let source = "1 and this_var_does_not_exist";
    match eval_source(source, &env()) {
        Err(InterpError::Eval(EvalError::TypeMismatch { expected, found, .. })) => {
            assert_eq!(expected, "bool");
            assert_eq!(found, "int");
        }
        other => panic!(
            "`{source}` must fail with TypeMismatch{{expected: \"bool\", found: \"int\"}} \
             from the left operand, without ever evaluating the right; got {other:?}"
        ),
    }
}

#[test]
fn documented_example_and_or_never_coerces_a_number_to_bool() {
    // From the README's worked example: `has_coupon and 5 or 0` -- `5` is
    // not a Bool, so this is a documented error case even though `5` is
    // "truthy" in many other languages. This language has no such
    // coercion anywhere.
    let mut environment = HashMap::new();
    environment.insert("has_coupon".to_string(), Value::Bool(true));

    let source = "has_coupon and 5 or 0";
    match eval_source(source, &environment) {
        Err(InterpError::Eval(EvalError::TypeMismatch { expected, found, .. })) => {
            assert_eq!(expected, "bool", "the right side of `and` must be required to be Bool, not truthy-coerced");
            assert_eq!(found, "int");
        }
        other => panic!(
            "`{source}` with has_coupon=true must fail with TypeMismatch (5 is not a Bool), got {other:?} \
             -- this language must not coerce numbers to booleans"
        ),
    }
}
