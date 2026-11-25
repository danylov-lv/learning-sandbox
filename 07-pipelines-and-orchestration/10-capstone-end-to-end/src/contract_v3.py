"""Scaffold for the capstone's evolved (v3) pandera contract.

Copy/adapt into wherever your DAG's contract_gate task imports from. This is
not a new pandera tutorial — you built v1/v2 contracts in earlier tasks;
this file only calls out what v3 changes and leaves the schema itself to
you.

Changes from whatever contract you already have:

1. `seller_rating` becomes optional. Before 2025-06-10 no record carries it
   at all; from that date on, valid records do. The contract must accept
   both shapes for the *same* schema instance — a valid row from
   2025-06-05 and a valid row from 2025-06-11 both pass, one without the
   column populated (or without the key present, depending on how you're
   modeling optional in a per-row dataframe check) and one with a float in
   [1.0, 5.0].

2. `price` must already be a numeric column by the time this schema
   validates it. From 2025-06-12 onward, the raw field is a locale-formatted
   string ("$1,299.00" US-style or "1.299,00 EUR" EU-style — the currency
   symbol/code tells you which locale, not a fixed rule per date). Do not
   put string-parsing logic inside the pandera check. Write a standalone
   function that takes a raw price value (str or number) and the record's
   currency, and returns a float or raises/flags on inputs it can't parse
   — call it as a normalization step *before* rows reach this schema, and
   unit-test it directly against both locale styles and plain numbers.

3. On 2025-06-15 (the CP2 drift drill), some fraction of records rename
   `currency` to `currency_code`. This is a NEW schema change — nothing in
   tasks 01-07 or the seed dataset's dt=06-01..14 days prepared you for it.
   Your contract needs to reject (quarantine, stage='contract') rows
   missing the `currency` key it expects, and your contract_gate task needs
   to recognize when a day's failure rate looks like a schema change (most
   failures share the same reason) rather than routine bad data, and fire a
   type='contract_drift' alert in that case rather than staying silent.

TODO: define the pandera schema (or ordinary validation function, if you
      prefer) for the v3 record shape, and a `normalize_price(raw_price,
      currency) -> float` helper as described in (2).
"""

from __future__ import annotations


def normalize_price(raw_price, currency: str) -> float:
    """Convert a raw price field (JSON number, or a locale-formatted
    string) into a plain float. Must handle:
      - plain JSON numbers (any date range)
      - US-style strings: symbol prefix, comma thousands, dot decimals
        (e.g. "$1,299.00")
      - EU-style strings: dot thousands, comma decimals, trailing currency
        code (e.g. "1.299,00 EUR")
    Raise (your choice of exception type) on anything else so the caller
    can route the record to quarantine instead of crashing the task.
    """
    raise NotImplementedError


def validate_batch(records):
    """Validate a batch of normalized records against the v3 contract.
    Return (passing, failing) or whatever shape your contract_gate task
    needs to route rows to core vs. ops.quarantine. Decide for yourself
    whether this is a pandera DataFrameSchema.validate(..., lazy=True) call
    or a hand-rolled per-row check — either is fine, the DAG only needs a
    clear pass/fail split with reasons attached to failures.
    """
    raise NotImplementedError
