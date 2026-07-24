#!/usr/bin/env bash
# Print three labeled JSON blocks to stdout -- see ../README.md for the
# exact required shape of each and the definition of each question.
#
# TODO:
#   ===Q1=== -- per-category obs_count + avg_price, glob over the Parquet dir
#   ===Q2=== -- per-region obs_count + avg_price, joining products.csv in
#   ===Q3=== -- per-product biggest single-step price jump (LAG window)
#
# Each block's body should be exactly the JSON array printed by one
# `duckdb -json -c "..."` call.

set -euo pipefail

echo "not implemented" >&2
exit 1
