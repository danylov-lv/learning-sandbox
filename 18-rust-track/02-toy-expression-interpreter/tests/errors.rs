//! An explicit error battery: every case asserts the exact `ParseError`/
//! `EvalError` *variant* and its exact `Position`, never just "it
//! returned `Err(..)`." This is what makes the error type genuinely
//! machine-comparable rather than a string message a human has to read.

use t02_toy_expression_interpreter::{ParseError, parse};

#[test]
fn unexpected_char_on_a_character_that_starts_no_token() {
    let source = "1 + @";
    // bytes: 0'1' 1' ' 2'+' 3' ' 4'@'
    match parse(source) {
        Err(ParseError::UnexpectedChar { ch, pos }) => {
            assert_eq!(ch, '@', "UnexpectedChar must carry the exact offending character");
            assert_eq!(pos.0, 4, "UnexpectedChar's position must be byte 4, where '@' starts");
        }
        other => panic!("`{source}` must fail with UnexpectedChar{{ch: '@', pos: 4}}, got {other:?}"),
    }
}

#[test]
fn lone_bang_without_equals_is_unexpected_char() {
    let source = "1 ! 2";
    match parse(source) {
        Err(ParseError::UnexpectedChar { ch, pos }) => {
            assert_eq!(ch, '!', "a lone '!' (not part of '!=') must be UnexpectedChar");
            assert_eq!(pos.0, 2, "'!' is at byte 2");
        }
        other => panic!("`{source}` must fail with UnexpectedChar{{ch: '!', pos: 2}}, got {other:?}"),
    }
}

#[test]
fn invalid_number_literal_too_large_for_i64() {
    let source = "99999999999999999999";
    match parse(source) {
        Err(ParseError::InvalidNumber { text, pos }) => {
            assert_eq!(text, "99999999999999999999", "InvalidNumber must carry the exact source text of the literal");
            assert_eq!(pos.0, 0, "the literal starts at byte 0");
        }
        other => panic!("`{source}` must fail with ParseError::InvalidNumber, got {other:?}"),
    }
}

#[test]
fn unbalanced_open_paren_is_unexpected_token_at_eof() {
    let source = "(1 + 2";
    match parse(source) {
        Err(ParseError::UnexpectedToken { expected, found, pos }) => {
            assert_eq!(expected, ")", "an unclosed '(' must report expected == \")\"");
            assert_eq!(found, "<eof>", "with nothing left to consume, found must be the literal \"<eof>\"");
            assert_eq!(pos.0, source.len(), "the eof position must be source.len()");
        }
        other => panic!("`{source}` must fail with UnexpectedToken{{expected: \")\", found: \"<eof>\"}}, got {other:?}"),
    }
}

#[test]
fn unbalanced_extra_close_paren_is_trailing_input() {
    let source = "(1 + 2))";
    // bytes: 0'(' 1'1' 2' ' 3'+' 4' ' 5'2' 6')' 7')'
    match parse(source) {
        Err(ParseError::TrailingInput { pos }) => {
            assert_eq!(pos.0, 7, "the extra unmatched ')' at byte 7 is trailing input, once `(1 + 2)` is already complete");
        }
        other => panic!("`{source}` must fail with TrailingInput at byte 7, got {other:?}"),
    }
}

#[test]
fn empty_input_expects_an_expression() {
    let source = "";
    match parse(source) {
        Err(ParseError::UnexpectedToken { expected, found, pos }) => {
            assert_eq!(expected, "expression", "empty input must report expected == \"expression\"");
            assert_eq!(found, "<eof>");
            assert_eq!(pos.0, 0);
        }
        other => panic!("`{source:?}` (empty) must fail with UnexpectedToken{{expected: \"expression\", found: \"<eof>\"}}, got {other:?}"),
    }
}

#[test]
fn operator_with_missing_right_operand_expects_an_expression() {
    let source = "1 +";
    match parse(source) {
        Err(ParseError::UnexpectedToken { expected, found, pos }) => {
            assert_eq!(expected, "expression");
            assert_eq!(found, "<eof>");
            assert_eq!(pos.0, 3, "eof position after `1 +` must be byte 3 (source.len())");
        }
        other => panic!("`{source}` must fail with UnexpectedToken{{expected: \"expression\", found: \"<eof>\"}}, got {other:?}"),
    }
}

#[test]
fn trailing_input_after_a_complete_expression() {
    let source = "1 2";
    // bytes: 0'1' 1' ' 2'2'
    match parse(source) {
        Err(ParseError::TrailingInput { pos }) => {
            assert_eq!(pos.0, 2, "the second '2' at byte 2 is unconsumed trailing input");
        }
        other => panic!("`{source}` must fail with TrailingInput at byte 2, got {other:?}"),
    }
}

#[test]
fn call_missing_comma_or_close_paren_reports_the_combined_expectation() {
    let source = "min(1 2)";
    // after parsing the first arg `1`, the parser expects "," or ")"
    // bytes: 0'm' 1'i' 2'n' 3'(' 4'1' 5' ' 6'2' 7')'
    match parse(source) {
        Err(ParseError::UnexpectedToken { expected, found, pos }) => {
            assert_eq!(expected, ", or )", "a call arg list expects either a comma or the closing paren next");
            assert_eq!(found, "2", "found must be the exact source text of the unexpected token");
            assert_eq!(pos.0, 6);
        }
        other => panic!("`{source}` must fail with UnexpectedToken{{expected: \", or )\", found: \"2\"}}, got {other:?}"),
    }
}

#[test]
fn keywords_are_reserved_and_cannot_be_used_as_bare_expression_start_incorrectly() {
    // "and" appearing where an expression is expected (nothing before it)
    // is itself a parse error, since "and" is a binary operator keyword,
    // not a valid primary.
    let source = "and 1";
    match parse(source) {
        Err(ParseError::UnexpectedToken { expected, found, pos }) => {
            assert_eq!(expected, "expression");
            assert_eq!(found, "and");
            assert_eq!(pos.0, 0);
        }
        other => panic!("`{source}` must fail with UnexpectedToken{{expected: \"expression\", found: \"and\"}}, got {other:?}"),
    }
}

#[test]
fn case_sensitive_keywords_true_is_keyword_but_true_capitalized_is_an_identifier() {
    use t02_toy_expression_interpreter::{Expr, Position};
    // "True" (capitalized) is not the `true` keyword -- it must parse as a
    // plain variable reference identifier named "True".
    let tree = parse("True").expect("`True` (capitalized) must parse as an identifier, not the `true` keyword");
    assert_eq!(
        tree,
        Expr::Var { name: "True".to_string(), pos: Position(0) },
        "keyword matching must be case-sensitive: `True` != `true`"
    );
}

#[test]
fn unterminated_string_at_eof_is_reported_at_the_opening_quote() {
    let source = "1 + \"never closed";
    match parse(source) {
        Err(ParseError::UnterminatedString { pos }) => {
            assert_eq!(pos.0, 4, "the opening quote of the unterminated string is at byte 4");
        }
        other => panic!("`{source}` must fail with UnterminatedString at byte 4, got {other:?}"),
    }
}

#[test]
fn invalid_escape_sequence_in_string_is_unexpected_char_at_the_backslash() {
    let source = r#""a\qb""#;
    // bytes: 0'"' 1'a' 2'\' 3'q' 4'b' 5'"'
    match parse(source) {
        Err(ParseError::UnexpectedChar { ch, pos }) => {
            assert_eq!(ch, 'q', "the invalid escape's character (after the backslash) must be carried");
            assert_eq!(pos.0, 2, "the position must be the backslash itself, byte 2");
        }
        other => panic!("`{source}` must fail with UnexpectedChar{{ch: 'q', pos: 2}}, got {other:?}"),
    }
}
