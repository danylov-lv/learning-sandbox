//! Structural/round-trip checks: `parse` must build the exact tree shape
//! the grammar implies, not just "an expression that happens to evaluate
//! right." A shortcut evaluator that computes an answer without ever
//! building a real `Expr` tree fails every test in this file, even if it
//! would pass every value-only test elsewhere in this suite.

use std::collections::HashMap;
use t02_toy_expression_interpreter::{BinaryOp, Expr, Position, UnaryOp, eval, parse};

#[test]
fn flat_addition_is_a_single_binary_node() {
    let source = "1 + 2";
    let tree = parse(source).expect("`1 + 2` is well-formed and must parse");
    let expected = Expr::Binary {
        op: BinaryOp::Add,
        left: Box::new(Expr::Int(1)),
        right: Box::new(Expr::Int(2)),
        pos: Position(2), // the '+' is the 3rd byte, index 2
    };
    assert_eq!(
        tree, expected,
        "`1 + 2` must parse to a single Add node over the two int literals, with pos at the operator"
    );
}

#[test]
fn precedence_shapes_the_tree_not_just_the_value() {
    // "1 + 2 * 3" must parse as Add(1, Mul(2, 3)) -- if precedence were
    // ignored and this parsed left-to-right instead, the tree would be
    // Mul(Add(1, 2), 3), which happens to evaluate to a *different* value
    // (9 vs the correct 7), so this also indirectly checks evaluation, but
    // the point of this test is the tree shape itself.
    let source = "1 + 2 * 3";
    let tree = parse(source).expect("`1 + 2 * 3` is well-formed and must parse");
    let expected = Expr::Binary {
        op: BinaryOp::Add,
        left: Box::new(Expr::Int(1)),
        right: Box::new(Expr::Binary {
            op: BinaryOp::Mul,
            left: Box::new(Expr::Int(2)),
            right: Box::new(Expr::Int(3)),
            pos: Position(6), // '*' at byte index 6: "1 + 2 * 3"
                               //                       0123456789
        }),
        pos: Position(2), // '+' at byte index 2
    };
    assert_eq!(
        tree, expected,
        "precedence must be encoded in the tree shape: '*' binds tighter, so it's the inner node"
    );
}

#[test]
fn parenthesized_grouping_overrides_precedence_in_the_tree() {
    let source = "(1 + 2) * 3";
    let tree = parse(source).expect("`(1 + 2) * 3` is well-formed and must parse");
    let expected = Expr::Binary {
        op: BinaryOp::Mul,
        left: Box::new(Expr::Binary {
            op: BinaryOp::Add,
            left: Box::new(Expr::Int(1)),
            right: Box::new(Expr::Int(2)),
            pos: Position(3), // '+' inside "(1 + 2) * 3"
                               //             0123456789
        }),
        right: Box::new(Expr::Int(3)),
        pos: Position(8), // '*' at byte index 8: "(1 + 2) * 3"
                           //                       01234567890
    };
    assert_eq!(
        tree, expected,
        "explicit parens must force Add to be the outer-evaluated... i.e. inner node under Mul"
    );
}

#[test]
fn unary_minus_wraps_its_operand() {
    let source = "-5";
    let tree = parse(source).expect("`-5` is well-formed and must parse");
    let expected = Expr::Unary {
        op: UnaryOp::Neg,
        expr: Box::new(Expr::Int(5)),
        pos: Position(0),
    };
    assert_eq!(
        tree, expected,
        "unary minus must produce a Unary node wrapping the literal, not a signed literal"
    );
}

#[test]
fn double_unary_minus_stacks_two_nodes() {
    let source = "- -5";
    let tree = parse(source).expect("`- -5` (double unary minus) is well-formed and must parse");
    let expected = Expr::Unary {
        op: UnaryOp::Neg,
        expr: Box::new(Expr::Unary {
            op: UnaryOp::Neg,
            expr: Box::new(Expr::Int(5)),
            pos: Position(2),
        }),
        pos: Position(0),
    };
    assert_eq!(
        tree, expected,
        "unary minus must be right-recursive and stack without collapsing into one node"
    );
}

#[test]
fn variable_reference_carries_its_position() {
    let source = "  price";
    let tree = parse(source).expect("a bare identifier is a well-formed variable reference");
    assert_eq!(
        tree,
        Expr::Var {
            name: "price".to_string(),
            pos: Position(2),
        },
        "Var must carry the identifier text and the byte position it started at"
    );
}

#[test]
fn call_node_carries_name_position_and_args_in_order() {
    let source = "max(1, 2)";
    let tree = parse(source).expect("`max(1, 2)` is a well-formed call");
    assert_eq!(
        tree,
        Expr::Call {
            name: "max".to_string(),
            args: vec![Expr::Int(1), Expr::Int(2)],
            pos: Position(0),
        },
        "Call must carry the function name, its arguments in source order, and the name's position"
    );
}

#[test]
fn comparison_and_boolean_layers_nest_as_the_grammar_says() {
    // "a and b or c" must parse as Or(And(a, b), c) since `or` binds
    // loosest and `and`/`or` group left-to-right at the same tier.
    let mut env = HashMap::new();
    env.insert("a".to_string(), t02_toy_expression_interpreter::Value::Bool(false));
    env.insert("b".to_string(), t02_toy_expression_interpreter::Value::Bool(false));
    env.insert("c".to_string(), t02_toy_expression_interpreter::Value::Bool(true));

    let source = "a and b or c";
    let tree = parse(source).expect("`a and b or c` is well-formed and must parse");
    let expected = Expr::Binary {
        op: BinaryOp::Or,
        left: Box::new(Expr::Binary {
            op: BinaryOp::And,
            left: Box::new(Expr::Var {
                name: "a".to_string(),
                pos: Position(0),
            }),
            right: Box::new(Expr::Var {
                name: "b".to_string(),
                pos: Position(6),
            }),
            pos: Position(2), // "and" starts at byte 2
        }),
        right: Box::new(Expr::Var {
            name: "c".to_string(),
            pos: Position(11),
        }),
        pos: Position(8), // "or" starts at byte 8: "a and b or c"
                           //                         012345678901
    };
    assert_eq!(
        tree, expected,
        "`or` must bind loosest: the tree's outer node must be Or, with And nested inside"
    );

    let value = eval(&tree, &env).expect("well-typed bool expression must evaluate without error");
    assert_eq!(
        value,
        t02_toy_expression_interpreter::Value::Bool(true),
        "(false and false) or true == true"
    );
}
