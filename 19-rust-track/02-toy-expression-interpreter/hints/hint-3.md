Concrete shape for each stage, in pseudocode. You still have to translate
this into working Rust (types, borrow-checking, exact error variants) --
nothing here is copy-pasteable.

## Tokenizer

```
cursor = 0
tokens = []
while cursor < source.len():
    skip any run of whitespace, advancing cursor
    if cursor >= source.len(): break
    start = cursor
    ch = char at cursor

    if ch is a digit:
        consume digits
        if char at cursor == '.' and char after that is a digit:
            consume '.', then consume digits  -> FloatLiteral(source[start..cursor])
        else:
            -> IntLiteral(source[start..cursor])

    else if ch is '"':
        advance past opening quote
        decoded = String::new()
        loop:
            if cursor >= len -> UnterminatedString{pos: start}
            next_ch = char at cursor
            if next_ch == '"': advance, break
            if next_ch == '\\':
                advance past backslash
                if cursor >= len -> UnterminatedString{pos: start}
                escape_ch = char at cursor
                match escape_ch: '"'/'\\'/'n'/'t' -> push decoded char, advance
                                 other -> UnexpectedChar{ch: escape_ch, pos: <backslash's position>}
            else:
                push next_ch to decoded, advance
        -> StringLiteral(decoded), pos = start

    else if ch is alphabetic or '_':
        consume identifier-shaped run
        text = source[start..cursor]
        match text: "and"/"or"/"not"/"true"/"false" -> that keyword's TokenKind
                    _ -> Ident(text)

    else:
        match ch:
            '+' -> Plus, advance 1
            '-' -> Minus, advance 1
            '*' -> Star, advance 1
            '/' -> Slash, advance 1
            '(' -> LParen, advance 1
            ')' -> RParen, advance 1
            ',' -> Comma, advance 1
            '=' -> if next char is '=': EqEq, advance 2
                   else: UnexpectedChar{ch: '=', pos: start}
            '!' -> if next char is '=': NotEq, advance 2
                   else: UnexpectedChar{ch: '!', pos: start}
            '<' -> if next char is '=': LtEq, advance 2  else: Lt, advance 1
            '>' -> if next char is '=': GtEq, advance 2  else: Gt, advance 1
            _   -> UnexpectedChar{ch, pos: start}

append Token{ Eof, pos: source.len() }
```

## Parser

One function per grammar tier, each returning `Result<Expr, ParseError>`.
Sketch of two representative tiers (the rest of the arithmetic/logical
tiers all follow the same `loop`-folding shape as `additive` below):

```
fn or_expr(p):
    left = and_expr(p)?
    while peek(p) == Or:
        op_pos = advance(p).pos
        right = and_expr(p)?
        left = Expr::Binary { op: Or, left: box(left), right: box(right), pos: op_pos }
    return left

fn comparison(p):
    left = additive(p)?
    if peek(p) is one of == != < <= > >=:
        op = advance(p)
        right = additive(p)?
        return Expr::Binary { op: <mapped from op.kind>, left: box(left), right: box(right), pos: op.pos }
    return left   // no `if`-branch taken: just the additive result, no comparison node

fn primary(p):
    tok = peek(p)
    match tok.kind:
        IntLiteral(text) -> parse text as i64 (InvalidNumber on failure), advance, return Expr::Int
        FloatLiteral(text) -> parse text as f64, advance, return Expr::Float
        StringLiteral(s) -> advance, return Expr::Str(s)
        True -> advance, return Expr::Bool(true)
        False -> advance, return Expr::Bool(false)
        Ident(name) ->
            advance
            if peek(p) == LParen:
                advance  // consume '('
                args = []
                if peek(p) != RParen:
                    loop:
                        args.push(expr(p)?)
                        if peek(p) == Comma: advance; continue
                        break
                expect RParen, else UnexpectedToken{expected: ", or )", found: <peek's text>, pos: <peek's pos>}
                advance  // consume ')'
                return Expr::Call { name, args, pos: <ident's own pos> }
            else:
                return Expr::Var { name, pos: <ident's own pos> }
        LParen ->
            advance
            inner = expr(p)?
            expect RParen, else UnexpectedToken{expected: ")", found: <peek's text or "<eof>">, pos: <peek's pos>}
            advance
            return inner
        _ -> UnexpectedToken{expected: "expression", found: <tok's text or "<eof>">, pos: tok.pos}

fn parse(source):
    tokens = tokenize(source)?
    p = Parser{tokens, pos: 0}
    tree = expr(&mut p)?
    if peek(&p) != Eof:
        return Err(TrailingInput{pos: peek(&p).pos})
    return Ok(tree)
```

## Evaluator

```
fn eval(expr, env):
    match expr:
        Int(n) -> Value::Int(n)
        Float(f) -> Value::Float(f)
        Str(s) -> Value::Str(s.clone())
        Bool(b) -> Value::Bool(b)

        Var{name, pos} -> env.get(name).cloned() or Err(UnknownVariable{name: name.clone(), pos})

        Unary{op: Neg, expr: inner, pos} ->
            v = eval(inner, env)?
            match v: Int(n) -> checked_neg(n) or Err(IntegerOverflow{pos})
                      Float(f) -> Value::Float(-f)
                      other -> Err(TypeMismatch{expected: "number", found: other.type_name(), pos})

        Unary{op: Not, expr: inner, pos} ->
            v = eval(inner, env)?
            match v: Bool(b) -> Value::Bool(!b)
                      other -> Err(TypeMismatch{expected: "bool", found: other.type_name(), pos})

        Binary{op: And, left, right, pos} ->
            lv = eval(left, env)?
            match lv:
                Bool(false) -> return Value::Bool(false)   // right never evaluated
                Bool(true)  -> rv = eval(right, env)?; match rv: Bool(b) -> Value::Bool(b)
                                                                  other -> Err(TypeMismatch{expected:"bool", found: other.type_name(), pos})
                other -> Err(TypeMismatch{expected: "bool", found: other.type_name(), pos})
            // Or is symmetric: swap the true/false branch

        Binary{op, left, right, pos} where op is + - * / == != < <= > >= ->
            lv = eval(left, env)?
            rv = eval(right, env)?
            apply_binary_op(op, lv, rv, pos)   // one helper, matches on op and on (lv, rv)'s variants

        Call{name, args, pos} ->
            match name.as_str():
                "min" | "max" -> if args.len() != 2: Err(WrongArgCount{name: "min"/"max", expected: 2, found: args.len(), pos})
                                  a = eval(&args[0], env)?; b = eval(&args[1], env)?
                                  require both are numbers (else TypeMismatch{expected:"number", .., pos})
                                  compare (int-exact if both Int, else via f64); return whichever Value wins (tie -> a)
                "round" -> if args.len() != 1: Err(WrongArgCount{name: "round", expected: 1, found: args.len(), pos})
                            v = eval(&args[0], env)?
                            match v: Int(n) -> Value::Int(n)
                                      Float(f) -> rounded = f.round(); check it fits in i64 range else IntegerOverflow{pos}; Value::Int(rounded as i64)
                                      other -> TypeMismatch{expected:"number", found: other.type_name(), pos}
                _ -> Err(UnknownFunction{name: name.clone(), pos})
```

The `apply_binary_op` helper is where the numeric-tower and comparison
rules from the README's tables live -- write it as one function matching
on `op` first, then on the two `Value`s, following the README's tables
row by row. It's the single largest function in the crate; that's
expected, and it's exactly the function the property-based tests in
`tests/property_random_trees.rs` are designed to fuzz hardest.
