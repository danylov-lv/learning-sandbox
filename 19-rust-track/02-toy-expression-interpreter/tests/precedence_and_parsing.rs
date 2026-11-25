//! Table-driven checks over precedence, associativity, unary minus, and
//! nested parentheses -- verified by evaluated `Value`, not just "it
//! parsed." Paired with `ast_structure.rs`, which checks the tree shape
//! directly for a handful of these same cases.

use std::collections::HashMap;
use t02_toy_expression_interpreter::{Value, eval_source};

fn env() -> HashMap<String, Value> {
    HashMap::new()
}

fn eval_int(source: &str) -> i64 {
    match eval_source(source, &env()) {
        Ok(Value::Int(n)) => n,
        other => panic!("expected Ok(Value::Int(_)) for `{source}`, got {other:?}"),
    }
}

fn eval_float(source: &str) -> f64 {
    match eval_source(source, &env()) {
        Ok(Value::Float(f)) => f,
        other => panic!("expected Ok(Value::Float(_)) for `{source}`, got {other:?}"),
    }
}

#[test]
fn precedence_and_associativity_table() {
    let cases: &[(&str, i64)] = &[
        ("1 + 2 * 3", 7), // * before +
        ("2 * 3 + 1", 7), // same, other order
        ("(1 + 2) * 3", 9), // parens override precedence
        ("2 * (3 + 1)", 8),
        ("10 - 2 - 3", 5), // left-associative: (10 - 2) - 3, not 10 - (2 - 3) = 11
        ("2 - 3 - 4", -5),
        ("20 - 4 * 2", 12), // * before -
        ("(20 - 4) * 2", 32),
        ("1 + 2 + 3 + 4", 10),
        ("2 * 2 * 2 * 2", 16),
        ("100 - 10 * 5", 50),
        ("(100 - 10) * 5", 450),
    ];
    for (source, expected) in cases {
        assert_eq!(
            eval_int(source),
            *expected,
            "`{source}` should evaluate to {expected} under standard precedence/left-associativity"
        );
    }
}

#[test]
fn unary_minus_binds_tighter_than_multiplicative() {
    let cases: &[(&str, i64)] = &[
        ("-2 * 3", -6),
        ("3 * -2", -6),
        ("-2 * -3", 6),
        ("-(2 * 3)", -6),
        ("- -5", 5),
        ("- - -5", -5),
        ("-2 + 3", 1),
        ("2 + -3", -1),
    ];
    for (source, expected) in cases {
        assert_eq!(
            eval_int(source),
            *expected,
            "`{source}`: unary minus must bind tighter than `*`/`+`/`-`, and stack via right-recursion"
        );
    }
}

#[test]
fn nested_parentheses_several_levels_deep() {
    let cases: &[(&str, i64)] = &[("((1 + 2))", 3), ("(((1 + 2)) * 3)", 9)];
    for (source, expected) in cases {
        assert_eq!(
            eval_int(source),
            *expected,
            "`{source}`: nested parens must compose correctly across several levels"
        );
    }
}

#[test]
fn division_always_promotes_inside_nested_parens() {
    // (1 + (2 * 3)) - (4 / 2) = (1 + 6) - (Float 2.0) => the whole
    // subtraction promotes to Float since the right operand is Float.
    let source = "(1 + (2 * 3)) - (4 / 2)";
    let f = eval_float(source);
    assert!(
        (f - 5.0).abs() < 1e-9,
        "`{source}` should evaluate to Float(5.0) (7 - 2.0), got {f}"
    );
}

#[test]
fn comparisons_do_not_chain_and_trailing_input_is_rejected() {
    use t02_toy_expression_interpreter::{InterpError, ParseError};

    let source = "1 < 2 < 3";
    let result = eval_source(source, &env());
    match result {
        Err(InterpError::Parse(ParseError::TrailingInput { pos })) => {
            // "1 < 2 < 3": the second '<' is the first leftover token.
            // b y t e s: 0'1' 1' ' 2'<' 3' ' 4'2' 5' ' 6'<' 7' ' 8'3'
            assert_eq!(
                pos.0, 6,
                "comparisons must not chain: after parsing `1 < 2`, the second `<` at byte 6 is trailing input"
            );
        }
        other => panic!(
            "`1 < 2 < 3` must fail to parse with TrailingInput at the second `<`, got {other:?}"
        ),
    }
}

#[test]
fn and_or_not_precedence_table() {
    let cases: &[(&str, bool)] = &[
        ("true and false", false),
        ("true or false", true),
        ("not true", false),
        ("not false", true),
        ("not not true", true),
        ("false or true and false", false), // and binds tighter: false or (true and false) = false or false
        ("true or true and false", true),   // true or (true and false) = true or false = true
        ("not true and false", false),      // (not true) and false = false and false = false
        ("not (true and false)", true),
    ];
    for (source, expected) in cases {
        let result = eval_source(source, &env());
        match result {
            Ok(Value::Bool(b)) => assert_eq!(
                b, *expected,
                "`{source}` should evaluate to Bool({expected}) under and/or/not precedence"
            ),
            other => panic!("expected Ok(Value::Bool({expected})) for `{source}`, got {other:?}"),
        }
    }
}
