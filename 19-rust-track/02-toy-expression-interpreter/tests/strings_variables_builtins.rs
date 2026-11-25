//! String literal decoding, variable lookup against a supplied `Env`, and
//! the three built-in functions (`min`, `max`, `round`).

use std::collections::HashMap;
use t02_toy_expression_interpreter::{EvalError, InterpError, Value, eval_source};

fn env() -> HashMap<String, Value> {
    HashMap::new()
}

#[test]
fn string_literal_round_trips_plain_text() {
    match eval_source(r#""hello world""#, &env()) {
        Ok(Value::Str(s)) => assert_eq!(s, "hello world", "a plain string literal must decode to its exact contents"),
        other => panic!("expected Value::Str(\"hello world\"), got {other:?}"),
    }
}

#[test]
fn string_literal_decodes_escapes() {
    let cases: &[(&str, &str)] = &[
        (r#""a\"b""#, "a\"b"),
        (r#""a\\b""#, "a\\b"),
        (r#""a\nb""#, "a\nb"),
        (r#""a\tb""#, "a\tb"),
    ];
    for (source, expected) in cases {
        match eval_source(source, &env()) {
            Ok(Value::Str(s)) => assert_eq!(
                s, *expected,
                "`{source}` should decode its escape sequence to {expected:?}"
            ),
            other => panic!("`{source}` must evaluate to Value::Str({expected:?}), got {other:?}"),
        }
    }
}

#[test]
fn unterminated_string_is_an_error() {
    use t02_toy_expression_interpreter::ParseError;
    let source = r#""abc"#; // opening quote at byte 0, never closed
    match eval_source(source, &env()) {
        Err(InterpError::Parse(ParseError::UnterminatedString { pos })) => {
            assert_eq!(pos.0, 0, "UnterminatedString's position must be the opening quote, byte 0");
        }
        other => panic!("`{source}` must fail with ParseError::UnterminatedString at byte 0, got {other:?}"),
    }
}

#[test]
fn string_equality_and_arithmetic_type_mismatch() {
    match eval_source(r#""a" + "b""#, &env()) {
        Err(InterpError::Eval(EvalError::TypeMismatch { expected, found, .. })) => {
            assert_eq!(expected, "number", "arithmetic on strings must report expected == \"number\"");
            assert_eq!(found, "string");
        }
        other => panic!("`\"a\" + \"b\"` must fail with TypeMismatch{{expected: \"number\", found: \"string\"}}, got {other:?}"),
    }
}

#[test]
fn variable_lookup_reads_from_the_supplied_env() {
    let mut environment = HashMap::new();
    environment.insert("price".to_string(), Value::Float(19.99));
    environment.insert("qty".to_string(), Value::Int(3));

    match eval_source("price * qty", &environment) {
        Ok(Value::Float(f)) => assert!(
            (f - 59.97).abs() < 1e-6,
            "`price * qty` with price=19.99, qty=3 should be ~59.97, got {f}"
        ),
        other => panic!("expected Value::Float(~59.97), got {other:?}"),
    }
}

#[test]
fn unknown_variable_reports_name_and_position() {
    let source = "1 + nonexistent";
    // b y t e s: 0'1' 1' ' 2'+' 3' ' 4..'nonexistent' starts at 4
    match eval_source(source, &env()) {
        Err(InterpError::Eval(EvalError::UnknownVariable { name, pos })) => {
            assert_eq!(name, "nonexistent", "UnknownVariable must carry the exact identifier text");
            assert_eq!(pos.0, 4, "UnknownVariable's position must point at the identifier, byte 4");
        }
        other => panic!("`{source}` must fail with UnknownVariable{{name: \"nonexistent\", pos: 4}}, got {other:?}"),
    }
}

#[test]
fn different_variables_in_env_do_not_leak_into_each_other() {
    // Anti-degenerate check: an implementation that ignores `env` and
    // always returns some fixed value would fail this (two different envs
    // over the same expression source must produce two different values).
    let mut env_a = HashMap::new();
    env_a.insert("x".to_string(), Value::Int(10));
    let mut env_b = HashMap::new();
    env_b.insert("x".to_string(), Value::Int(20));

    let a = eval_source("x * 2", &env_a);
    let b = eval_source("x * 2", &env_b);
    assert_eq!(a, Ok(Value::Int(20)), "x=10 -> x*2 == 20");
    assert_eq!(b, Ok(Value::Int(40)), "x=20 -> x*2 == 40");
    assert_ne!(a, b, "the same source expression must evaluate differently against different envs");
}

#[test]
fn min_max_preserve_the_winning_operands_original_type() {
    match eval_source("min(3, 5)", &env()) {
        Ok(Value::Int(3)) => {}
        other => panic!("`min(3, 5)` must be Value::Int(3), got {other:?}"),
    }
    match eval_source("max(3, 5)", &env()) {
        Ok(Value::Int(5)) => {}
        other => panic!("`max(3, 5)` must be Value::Int(5), got {other:?}"),
    }
    // Mixed Int/Float: the winning argument keeps its own original type.
    match eval_source("min(3, 5.5)", &env()) {
        Ok(Value::Int(3)) => {}
        other => panic!("`min(3, 5.5)` must be Value::Int(3) (3's own type preserved), got {other:?}"),
    }
    match eval_source("min(3.5, 5)", &env()) {
        Ok(Value::Float(f)) if (f - 3.5).abs() < 1e-9 => {}
        other => panic!("`min(3.5, 5)` must be Value::Float(3.5) (3.5's own type preserved), got {other:?}"),
    }
    match eval_source("max(2, 2.0)", &env()) {
        // tie -> return the FIRST argument's value: Int(2), not Float(2.0)
        Ok(Value::Int(2)) => {}
        other => panic!("`max(2, 2.0)` is a tie: must return the first argument's Value::Int(2), got {other:?}"),
    }
}

#[test]
fn round_passes_ints_through_and_rounds_floats_ties_away_from_zero() {
    match eval_source("round(5)", &env()) {
        Ok(Value::Int(5)) => {}
        other => panic!("`round(5)` on an Int must return it unchanged as Value::Int(5), got {other:?}"),
    }
    let cases: &[(&str, i64)] = &[
        ("round(2.4)", 2),
        ("round(2.6)", 3),
        ("round(2.5)", 3),   // tie rounds away from zero
        ("round(-2.5)", -3), // tie rounds away from zero
        ("round(-2.4)", -2),
    ];
    for (source, expected) in cases {
        match eval_source(source, &env()) {
            Ok(Value::Int(n)) => assert_eq!(n, *expected, "`{source}` should round to {expected}"),
            other => panic!("`{source}` must evaluate to Value::Int({expected}), got {other:?}"),
        }
    }
}

#[test]
fn unknown_function_reports_name_and_position() {
    let source = "1 + frobnicate(2)";
    // "frobnicate" identifier starts at byte 4
    match eval_source(source, &env()) {
        Err(InterpError::Eval(EvalError::UnknownFunction { name, pos })) => {
            assert_eq!(name, "frobnicate");
            assert_eq!(pos.0, 4, "UnknownFunction's position must point at the call name, byte 4");
        }
        other => panic!("`{source}` must fail with UnknownFunction{{name: \"frobnicate\", pos: 4}}, got {other:?}"),
    }
}

#[test]
fn wrong_arg_count_is_checked_before_evaluating_arguments() {
    // The single arg references an unknown variable; if arg-count were
    // checked after evaluating arguments, this would report
    // UnknownVariable instead of WrongArgCount.
    match eval_source("min(1)", &env()) {
        Err(InterpError::Eval(EvalError::WrongArgCount { name, expected, found, .. })) => {
            assert_eq!(name, "min");
            assert_eq!(expected, 2);
            assert_eq!(found, 1);
        }
        other => panic!("`min(1)` must fail with WrongArgCount{{name: \"min\", expected: 2, found: 1}}, got {other:?}"),
    }
    match eval_source("round(1, 2)", &env()) {
        Err(InterpError::Eval(EvalError::WrongArgCount { name, expected, found, .. })) => {
            assert_eq!(name, "round");
            assert_eq!(expected, 1);
            assert_eq!(found, 2);
        }
        other => panic!("`round(1, 2)` must fail with WrongArgCount{{name: \"round\", expected: 1, found: 2}}, got {other:?}"),
    }
    match eval_source("round(unknown_var, unknown_var2)", &env()) {
        Err(InterpError::Eval(EvalError::WrongArgCount { name, .. })) => {
            assert_eq!(name, "round", "arg count must be checked before arguments are evaluated at all");
        }
        other => panic!(
            "`round(unknown_var, unknown_var2)` must fail with WrongArgCount (checked before \
             evaluating the unknown-variable arguments), got {other:?}"
        ),
    }
}

#[test]
fn builtin_argument_type_mismatch() {
    match eval_source(r#"min(1, "a")"#, &env()) {
        Err(InterpError::Eval(EvalError::TypeMismatch { expected, found, .. })) => {
            assert_eq!(expected, "number");
            assert_eq!(found, "string");
        }
        other => panic!(r#"`min(1, "a")` must fail with TypeMismatch{{expected: "number", found: "string"}}, got {other:?}"#),
    }
}
