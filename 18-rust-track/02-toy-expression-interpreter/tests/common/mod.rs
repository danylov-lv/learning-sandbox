//! Shared support for the property-based test: a tiny generator for random
//! well-formed arithmetic expression trees (`Node`), a renderer that turns
//! a tree into fully-parenthesized source text (so precedence ambiguity
//! never enters the picture -- precedence itself is covered by the
//! dedicated table-driven tests elsewhere), and an *independent* evaluator
//! over `Node` that never calls into the crate under test at all. The
//! property test compares the crate's `eval_source` output for the
//! rendered text against this independent evaluation of the same tree.
//!
//! Every leaf's magnitude and the tree's max depth are bounded so that
//! plain (non-checked) `i64` arithmetic here can never overflow -- this
//! reference evaluator intentionally does not need `EvalError::
//! IntegerOverflow` handling, since overflow is already exercised directly
//! in `tests/numeric_tower.rs`.

use sandbox18_harness::prng::Xorshift64;
use t02_toy_expression_interpreter::Value;

#[derive(Debug, Clone)]
pub enum Node {
    IntLeaf(i64),
    /// The exact literal text (e.g. "13.7"), so both this reference
    /// evaluator and the crate's own tokenizer parse the identical string
    /// with `str::parse::<f64>()` -- no risk of the two computing a
    /// same-value-but-different-bit-pattern float from two different
    /// arithmetic paths.
    FloatLeaf(String),
    Neg(Box<Node>),
    Add(Box<Node>, Box<Node>),
    Sub(Box<Node>, Box<Node>),
    Mul(Box<Node>, Box<Node>),
    /// The divisor is always generated as a fresh nonzero leaf (see
    /// `gen_node`), never an arbitrary subtree -- this guarantees no
    /// generated tree ever divides by a computed zero.
    Div(Box<Node>, Box<Node>),
}

#[derive(Debug, Clone, Copy)]
enum NumKind {
    Int(i64),
    Float(f64),
}

fn as_f64(k: NumKind) -> f64 {
    match k {
        NumKind::Int(n) => n as f64,
        NumKind::Float(f) => f,
    }
}

/// The reference evaluator: mirrors this language's numeric-tower rule
/// (int op int stays int; any float operand promotes; division always
/// promotes) using plain Rust arithmetic, entirely independent of
/// anything in `t02_toy_expression_interpreter`.
fn eval_node(node: &Node) -> NumKind {
    match node {
        Node::IntLeaf(n) => NumKind::Int(*n),
        Node::FloatLeaf(text) => NumKind::Float(
            text.parse::<f64>()
                .expect("generator only ever renders syntactically valid float literals"),
        ),
        Node::Neg(inner) => match eval_node(inner) {
            NumKind::Int(n) => NumKind::Int(-n),
            NumKind::Float(f) => NumKind::Float(-f),
        },
        Node::Add(l, r) => arith(eval_node(l), eval_node(r), |a, b| a + b, |a, b| a + b),
        Node::Sub(l, r) => arith(eval_node(l), eval_node(r), |a, b| a - b, |a, b| a - b),
        Node::Mul(l, r) => arith(eval_node(l), eval_node(r), |a, b| a * b, |a, b| a * b),
        Node::Div(l, r) => {
            let numerator = as_f64(eval_node(l));
            let divisor = as_f64(eval_node(r));
            NumKind::Float(numerator / divisor)
        }
    }
}

fn arith(a: NumKind, b: NumKind, int_op: fn(i64, i64) -> i64, float_op: fn(f64, f64) -> f64) -> NumKind {
    match (a, b) {
        (NumKind::Int(x), NumKind::Int(y)) => NumKind::Int(int_op(x, y)),
        (x, y) => NumKind::Float(float_op(as_f64(x), as_f64(y))),
    }
}

pub fn eval_node_as_value(node: &Node) -> Value {
    match eval_node(node) {
        NumKind::Int(n) => Value::Int(n),
        NumKind::Float(f) => Value::Float(f),
    }
}

/// Renders a tree to fully-parenthesized source text: every binary
/// operation and every negation is wrapped in its own parens, so the
/// evaluation order is unambiguous regardless of the language's operator
/// precedence rules.
pub fn render(node: &Node) -> String {
    match node {
        Node::IntLeaf(n) => n.to_string(),
        Node::FloatLeaf(text) => text.clone(),
        Node::Neg(inner) => format!("-({})", render(inner)),
        Node::Add(l, r) => format!("({} + {})", render(l), render(r)),
        Node::Sub(l, r) => format!("({} - {})", render(l), render(r)),
        Node::Mul(l, r) => format!("({} * {})", render(l), render(r)),
        Node::Div(l, r) => format!("({} / {})", render(l), render(r)),
    }
}

/// A fresh leaf: an `Int` in `1..=20` or a `Float` in `1.0..=20.9` (one
/// decimal digit) -- always strictly positive, so it's always safe to use
/// as a divisor.
fn gen_leaf(rng: &mut Xorshift64) -> Node {
    if rng.next_f64() < 0.5 {
        Node::IntLeaf(rng.gen_range(1, 21) as i64)
    } else {
        let whole = rng.gen_range(1, 21);
        let tenths = rng.gen_range(0, 10);
        Node::FloatLeaf(format!("{whole}.{tenths}"))
    }
}

/// Generates a random tree up to `max_depth` levels deep. `max_depth` must
/// stay small (3 is the value this suite uses) so that a pure-int
/// multiplicative chain has no realistic path to overflowing `i64` in the
/// reference evaluator above.
pub fn gen_node(rng: &mut Xorshift64, max_depth: u32) -> Node {
    if max_depth == 0 || rng.next_f64() < 0.35 {
        return gen_leaf(rng);
    }
    match rng.gen_range(0, 5) {
        0 => Node::Add(
            Box::new(gen_node(rng, max_depth - 1)),
            Box::new(gen_node(rng, max_depth - 1)),
        ),
        1 => Node::Sub(
            Box::new(gen_node(rng, max_depth - 1)),
            Box::new(gen_node(rng, max_depth - 1)),
        ),
        2 => Node::Mul(
            Box::new(gen_node(rng, max_depth - 1)),
            Box::new(gen_node(rng, max_depth - 1)),
        ),
        3 => Node::Div(
            Box::new(gen_node(rng, max_depth - 1)),
            Box::new(gen_leaf(rng)), // fresh nonzero leaf divisor, not a subtree
        ),
        _ => Node::Neg(Box::new(gen_node(rng, max_depth - 1))),
    }
}

/// Exact equality for `Int`, tolerance-based for `Float` (defensive --
/// operations on identical operands in identical order should be
/// bit-exact under IEEE 754, but a tolerance avoids any flakiness from an
/// equally-valid alternate evaluation order).
pub fn values_match(actual: &Value, expected: &Value) -> bool {
    match (actual, expected) {
        (Value::Int(a), Value::Int(b)) => a == b,
        (Value::Float(a), Value::Float(b)) => {
            let scale = a.abs().max(b.abs()).max(1.0);
            (a - b).abs() < scale * 1e-9
        }
        _ => false,
    }
}
