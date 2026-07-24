"""Console entry point for pricelib. Given, not edited."""

from __future__ import annotations

from pricelib import __version__, summarize

SAMPLE_PRICES = [12.5, 7.25, 30.0, 4.99]


def main() -> None:
    stats = summarize(SAMPLE_PRICES)
    print(f"pricelib {__version__}: count={stats['count']} avg={stats['avg']:.2f}")


if __name__ == "__main__":
    main()
