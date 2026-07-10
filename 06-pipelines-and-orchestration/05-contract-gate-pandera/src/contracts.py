"""Pandera contract for the staging -> core boundary.

This is the gate: every row read out of staging.price_records_raw for a given
day must pass this schema before it is allowed into core.price_records. Rows
that fail go to ops.quarantine instead, with the pandera failure reason
attached.

Fill in PRICE_RECORD_SCHEMA below. TODOs mark the business rules the schema
needs to express. Nothing here talks to Postgres or Airflow — that lives in
the DAG (see the module README for the DAG-skeleton convention: write your
version into dags/, this file is a library import from there).
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera.pandas import Column, Check

# Allowed currency codes for this task's scope. Do not add more here without
# re-reading what the ground truth actually contains for the days you're
# validating against.
ALLOWED_CURRENCIES = ["USD", "EUR", "GBP"]

# TODO: fill in one ceiling per category. A single flat number across all
# categories will NOT work: an absurd price for a cheap category is still
# far below a perfectly normal price for an expensive one, so the ceiling
# has to be category-relative. Derive the values from the data itself —
# look at each category's price distribution and find where the legitimate
# tail ends and the planted junk begins (there is a visible gap; you don't
# need the exact boundary, anywhere inside the gap works).
ABSURD_PRICE_CEILING_BY_CATEGORY: dict[str, float] = {
    # "electronics": ...,
}

PRICE_RECORD_SCHEMA = pa.DataFrameSchema(
    columns={
        # TODO: one Column entry per field in the record contract.
        #
        # Required, non-null, typed fields: source_site, product_url, title,
        # category, price, currency, in_stock, scraped_at.
        #
        # Business rules to express as Checks (not an exhaustive list, think
        # about what else the contract should catch):
        #   - price > 0 and below the category's absurdity ceiling (a
        #     cross-column rule — a per-Column Check only sees its own
        #     column, so this one needs a DataFrame-level check or a
        #     different placement)
        #   - currency isin ALLOWED_CURRENCIES
        #   - product_url non-null and matches the expected URL shape
        #   - scraped_at falls within the partition day being validated
        #     (this one needs a value only known at validation time, not at
        #     schema-definition time — think about where that check has to
        #     live: a static Column Check here, or a check done by the DAG
        #     after calling .validate(), or a schema built per-call)
    },
    strict=True,
    coerce=True,
)


def validate_day(df, dt):
    """Validate a day's frame against the contract.

    TODO: call PRICE_RECORD_SCHEMA.validate(df, lazy=True) and return
    something the DAG can use to split passing rows from failing ones plus
    per-row failure reasons. Pandera's lazy validation raises a
    SchemaErrors exception carrying a `.failure_cases` DataFrame when there
    are any failures — look at what columns that DataFrame has before
    deciding how to map failures back to quarantine reasons.

    `dt` is the partition day (a date), needed for the scraped_at-in-range
    check mentioned above.
    """
    raise NotImplementedError
