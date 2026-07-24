# Hint 3

Shapes to aim for (work out the bodies yourself — the test file already
tells you the exact expected behavior for each):

```python
def clean_price(value: str) -> float: ...

def parse_optional_tag(tag: str | None = None) -> str: ...

def to_currency_code(code: str) -> str: ...  # signature unchanged — fix the *body*

def batch_normalize(prices: list[str]) -> list[float]: ...
```

For `parse_optional_tag`: what should the function return when `tag` is
`None`, per `test_parse_optional_tag_with_none`? Branch on it before
calling any string method.

For `to_currency_code`: `test_to_currency_code_invalid_raises` expects a
`ValueError`, not a `None`. A function typed `-> str` that can't produce
a `str` for some input has exactly one strict-mode-compatible option
that isn't returning a sentinel.

Then set `strict = true` in `[tool.mypy]` and re-run `mypy src` until it
reports zero errors.
