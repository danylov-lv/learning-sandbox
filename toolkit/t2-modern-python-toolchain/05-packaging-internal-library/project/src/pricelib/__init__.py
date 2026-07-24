"""Internal price-summary library. Given, not edited.

Packaged and distributed as a wheel/sdist by this task — not run from a
checked-out source tree.
"""

__version__ = "0.4.0"


def summarize(prices: list[float]) -> dict[str, float]:
    if not prices:
        return {"count": 0, "min": 0.0, "max": 0.0, "avg": 0.0}
    return {
        "count": len(prices),
        "min": min(prices),
        "max": max(prices),
        "avg": sum(prices) / len(prices),
    }
