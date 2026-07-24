def clean_price(value):
    """Strip currency symbols and thousands separators, return a float."""
    text = value.strip().replace("$", "").replace(",", "")
    return float(text)


def parse_optional_tag(tag=None):
    """Normalize a tag: lowercase and strip, or '' if none was given."""
    return tag.strip().lower()


def to_currency_code(code: str) -> str:
    """Uppercase a 3-letter currency code."""
    if len(code) == 3:
        return code.upper()
    return None


def batch_normalize(prices):
    """Clean a list of raw price strings into floats."""
    result = []
    for p in prices:
        result.append(clean_price(p))
    return result
