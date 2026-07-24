"""Fixture data for the pricetool CLI. Given, not edited.

The config is embedded as a YAML string (rather than a separate file on
disk) so the CLI behaves identically whether it's run from the source tree
(`uv run pricetool`) or from a built, installed package
(`uv tool run --from . pricetool`) — no extra data files to ship in the
wheel.
"""

PRICES: list[float] = [19.99, 5.50, 42.00, 13.25, 8.75]

CONFIG_YAML = """
currency: USD
"""
