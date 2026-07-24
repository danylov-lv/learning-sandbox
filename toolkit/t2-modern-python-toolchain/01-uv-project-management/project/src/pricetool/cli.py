"""The pricetool console entry point. Given, not edited.

Depends on PyYAML to parse the embedded config — that dependency is
missing from pyproject.toml in the starting state, which is the point.
"""

from __future__ import annotations

import yaml

from pricetool.data import CONFIG_YAML, PRICES


def main() -> None:
    config = yaml.safe_load(CONFIG_YAML)
    currency = config["currency"]
    count = len(PRICES)
    avg = sum(PRICES) / count
    print(
        f"count={count} min={min(PRICES):.2f} max={max(PRICES):.2f} "
        f"avg={avg:.2f} currency={currency}"
    )


if __name__ == "__main__":
    main()
