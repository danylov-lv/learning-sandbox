//! t02-toy-expression-interpreter -- scaffold.
//!
//! Tokenizer + recursive-descent parser + evaluator for a small expression
//! language. See `README.md` for the full grammar and evaluation semantics
//! -- it is the spec every test in `tests/` is written against.
//!
//! Every function body below is `todo!()`. The declared types (`Token`,
//! `Expr`, `Value`, `ParseError`, `EvalError`, ...) are themselves part of
//! the graded API: their variants and fields are what `tests/` constructs
//! and matches against, so do not rename or restructure them -- implement
//! the functions that produce and consume them.

use std::collections::HashMap;

/// A byte offset (0-based) into the original source `&str`. Never a char
/// index -- always index directly into the source's bytes/`str` slicing.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Position(pub usize);

/// The kind of a single token, borrowing from the source where possible.
#[derive(Debug, Clone, PartialEq)]
pub enum TokenKind<'a> {
    IntLiteral(&'a str),
    FloatLiteral(&'a str),
    /// Decoded string content (escapes already resolved) -- necessarily
    /// owned, since the decoded text can differ from the source bytes.
    StringLiteral(String),
    Ident(&'a str),
    And,
    Or,
    Not,
    True,
    False,
    Plus,
    Minus,
    Star,
    Slash,
    EqEq,
    NotEq,
    Lt,
    LtEq,
    Gt,
    GtEq,
    LParen,
    RParen,
    Comma,
    Eof,
}

/// A token plus the position of its first byte in the source.
#[derive(Debug, Clone, PartialEq)]
pub struct Token<'a> {
    pub kind: TokenKind<'a>,
    pub pos: Position,
}

/// Unary operators. See README "Values and the numeric tower".
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UnaryOp {
    Neg,
    Not,
}

/// Binary operators. See README "Values and the numeric tower".
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BinaryOp {
    Add,
    Sub,
    Mul,
    Div,
    Eq,
    NotEq,
    Lt,
    LtEq,
    Gt,
    GtEq,
    And,
    Or,
}

/// The parsed abstract syntax tree. `Box<Expr>` gives the recursive
/// variants a known size; `Position` on the non-literal variants is where
/// an `EvalError` produced by that node points.
#[derive(Debug, Clone, PartialEq)]
pub enum Expr {
    Int(i64),
    Float(f64),
    Str(String),
    Bool(bool),
    Var {
        name: String,
        pos: Position,
    },
    Unary {
        op: UnaryOp,
        expr: Box<Expr>,
        pos: Position,
    },
    Binary {
        op: BinaryOp,
        left: Box<Expr>,
        right: Box<Expr>,
        pos: Position,
    },
    Call {
        name: String,
        args: Vec<Expr>,
        pos: Position,
    },
}

/// A runtime value. See README for the promotion/comparison rules between
/// variants.
#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Int(i64),
    Float(f64),
    Str(String),
    Bool(bool),
}

impl Value {
    /// One of `"int"`, `"float"`, `"string"`, `"bool"` -- the only strings
    /// ever placed in an `EvalError`'s `found` field.
    pub fn type_name(&self) -> &'static str {
        todo!()
    }
}

/// The variable environment `eval` reads `Expr::Var` lookups from.
pub type Env = HashMap<String, Value>;

/// Errors raised while tokenizing or parsing. Every variant carries the
/// `Position` of the offending token. See README "Parse errors" for the
/// exact `expected`/`found` string contract on `UnexpectedToken`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ParseError {
    UnexpectedChar {
        ch: char,
        pos: Position,
    },
    UnterminatedString {
        pos: Position,
    },
    InvalidNumber {
        text: String,
        pos: Position,
    },
    UnexpectedToken {
        expected: &'static str,
        found: String,
        pos: Position,
    },
    TrailingInput {
        pos: Position,
    },
}

/// Errors raised while evaluating a parsed `Expr`. Every variant carries
/// the `Position` of the node that raised it. See README "Values and the
/// numeric tower" / "Built-in functions" for exactly when each fires.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EvalError {
    DivisionByZero {
        pos: Position,
    },
    TypeMismatch {
        expected: &'static str,
        found: &'static str,
        pos: Position,
    },
    UnknownVariable {
        name: String,
        pos: Position,
    },
    UnknownFunction {
        name: String,
        pos: Position,
    },
    WrongArgCount {
        name: &'static str,
        expected: usize,
        found: usize,
        pos: Position,
    },
    IntegerOverflow {
        pos: Position,
    },
}

/// Combines both error types for `eval_source`'s single `Result`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InterpError {
    Parse(ParseError),
    Eval(EvalError),
}

impl From<ParseError> for InterpError {
    fn from(err: ParseError) -> Self {
        let _ = err;
        todo!()
    }
}

impl From<EvalError> for InterpError {
    fn from(err: EvalError) -> Self {
        let _ = err;
        todo!()
    }
}

/// Turns `source` into a token stream, ending with a single `TokenKind::Eof`
/// token at `Position(source.len())`. See README "Grammar" and "Parse
/// errors" for the lexical rules and error cases.
pub fn tokenize(source: &str) -> Result<Vec<Token<'_>>, ParseError> {
    let _ = source;
    todo!()
}

/// Tokenizes and parses `source` into a single `Expr`, rejecting any
/// trailing input after a complete expression (`ParseError::TrailingInput`).
/// See README "Grammar" for the full EBNF and precedence table.
pub fn parse(source: &str) -> Result<Expr, ParseError> {
    let _ = source;
    todo!()
}

/// Evaluates a parsed `Expr` against `env`. See README "Values and the
/// numeric tower" / "Variables" / "Built-in functions" for the exact
/// evaluation semantics, including the `and`/`or` short-circuit rules and
/// the argument-evaluation order for calls.
pub fn eval(expr: &Expr, env: &Env) -> Result<Value, EvalError> {
    let _ = (expr, env);
    todo!()
}

/// Convenience: `parse` then `eval`, unifying both error types.
pub fn eval_source(source: &str, env: &Env) -> Result<Value, InterpError> {
    let _ = (source, env);
    todo!()
}
