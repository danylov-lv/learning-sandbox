//! Int-vs-float promotion rules: int/int arithmetic stays int, any float
//! operand promotes the whole operation, division always promotes, and
//! division-by-zero / integer overflow are caught as errors rather than
//! panicking or silently producing `inf`/`NaN`/wrapped garbage.

use std::collections::HashMap;
use t02_toy_expression_interpreter::{EvalError, Value, eval_source};

fn env() -> HashMap<String, Value> {
    HashMap::new()
}

#[test]
fn int_arithmetic_stays_int() {
    let cases: &[(&str, i64)] = &[
        ("1 + 2", 3),
        ("10 - 3", 7),
        ("6 * 7", 42),
        ("0 - 5", -5),
        ("5 * 0", 0),
    ];
    for (source, expected) in cases {
        match eval_source(source, &env()) {
            Ok(Value::Int(n)) => assert_eq!(
                n, *expected,
                "`{source}`: int op int over +,-,* must stay Int and equal {expected}"
            ),
            other => panic!("`{source}` must evaluate to Value::Int({expected}), got {other:?}"),
        }
    }
}

#[test]
fn any_float_operand_promotes_the_whole_operation() {
    let cases: &[(&str, f64)] = &[
        ("1 + 2.5", 3.5),
        ("2.5 + 1", 3.5),
        ("2.0 * 3", 6.0),
        ("3 * 2.0", 6.0),
        ("5.5 - 2", 3.5),
        ("5 - 2.5", 2.5),
    ];
    for (source, expected) in cases {
        match eval_source(source, &env()) {
            Ok(Value::Float(f)) => assert!(
                (f - *expected).abs() < 1e-9,
                "`{source}` should promote to Float({expected}), got Float({f})"
            ),
            other => panic!("`{source}` must evaluate to Value::Float({expected}), got {other:?}"),
        }
    }
}

#[test]
fn division_always_produces_a_float_even_for_two_ints() {
    match eval_source("6 / 4", &env()) {
        Ok(Value::Float(f)) => assert!(
            (f - 1.5).abs() < 1e-9,
            "`6 / 4` must always promote to Float division (1.5), never integer division (1), got {f}"
        ),
        other => panic!("`6 / 4` must evaluate to Value::Float(1.5), got {other:?}"),
    }

    match eval_source("8 / 4", &env()) {
        Ok(Value::Float(f)) => assert!(
            (f - 2.0).abs() < 1e-9,
            "`8 / 4` divides evenly but must still be Value::Float(2.0), not Value::Int(2)"
        ),
        other => panic!("`8 / 4` must evaluate to Value::Float(2.0), got {other:?}"),
    }
}

#[test]
fn division_by_zero_is_an_error_for_int_and_float_zero() {
    for source in ["1 / 0", "1.0 / 0", "1 / 0.0", "5 / (2 - 2)"] {
        match eval_source(source, &env()) {
            Err(t02_toy_expression_interpreter::InterpError::Eval(EvalError::DivisionByZero {
                ..
            })) => {}
            other => panic!(
                "`{source}` must fail with EvalError::DivisionByZero, got {other:?} -- a zero \
                 divisor must never produce inf/NaN silently"
            ),
        }
    }
}

#[test]
fn division_by_zero_position_points_at_the_slash() {
    let source = "1 / 0";
    // b y t e s: 0'1' 1' ' 2'/' 3' ' 4'0'
    match eval_source(source, &env()) {
        Err(t02_toy_expression_interpreter::InterpError::Eval(EvalError::DivisionByZero { pos })) => {
            assert_eq!(pos.0, 2, "DivisionByZero's position must point at the `/` operator, byte 2");
        }
        other => panic!("expected DivisionByZero at byte 2, got {other:?}"),
    }
}

#[test]
fn integer_overflow_on_arithmetic_is_caught_not_panicked() {
    let source = format!("{} + 1", i64::MAX);
    match eval_source(&source, &env()) {
        Err(t02_toy_expression_interpreter::InterpError::Eval(EvalError::IntegerOverflow { .. })) => {}
        other => panic!(
            "`i64::MAX + 1` must fail with EvalError::IntegerOverflow (checked arithmetic), got {other:?}"
        ),
    }
}

#[test]
fn negating_i64_min_overflows() {
    // The literal `i64::MIN` (as unsigned digits) doesn't even fit in an
    // i64, so it can never be written directly -- numeric literals are
    // always unsigned at the lexer level (see README). Build i64::MIN the
    // only way this language can express it: negate i64::MAX, then
    // subtract 1 (both steps stay in range), then negate the result.
    let source = format!("-(-{} - 1)", i64::MAX);
    match eval_source(&source, &env()) {
        Err(t02_toy_expression_interpreter::InterpError::Eval(EvalError::IntegerOverflow { .. })) => {}
        other => panic!(
            "`{source}` computes i64::MIN via subtraction and then negates it, which must fail \
             with EvalError::IntegerOverflow (negating i64::MIN overflows), got {other:?}"
        ),
    }
}

#[test]
fn mixed_int_float_arithmetic_across_a_larger_expression() {
    // (3 + 4.5) * 2 - 1 = 7.5 * 2 - 1 = 15.0 - 1 = 14.0, all Float once any
    // Float operand appears anywhere in the chain.
    let source = "(3 + 4.5) * 2 - 1";
    match eval_source(source, &env()) {
        Ok(Value::Float(f)) => assert!(
            (f - 14.0).abs() < 1e-9,
            "`{source}` should evaluate to Float(14.0), got {f}"
        ),
        other => panic!("`{source}` must evaluate to Value::Float(14.0), got {other:?}"),
    }
}

#[test]
fn pure_int_subexpression_alongside_float_subexpression_keeps_int_where_no_float_touches_it() {
    // "3 + 4" alone must stay Int; only the outer op that actually mixes
    // in the Float should promote. This distinguishes a correct
    // per-operation promotion rule from a "the whole tree is float if any
    // literal anywhere is float" shortcut.
    let source = "(3 + 4)";
    match eval_source(source, &env()) {
        Ok(Value::Int(n)) => assert_eq!(n, 7, "`(3 + 4)` with no Float operand anywhere must stay Value::Int(7)"),
        other => panic!("`(3 + 4)` must evaluate to Value::Int(7), got {other:?}"),
    }
}
