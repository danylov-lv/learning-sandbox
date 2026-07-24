#!/usr/bin/env bash
# Print, to stdout, a JSON array with one object per category — see
# ../README.md for the exact required shape (category, listing_count,
# avg_price_usd, tier_counts).
#
# The two input files:
#   ../data/scraped/catalog.json  -- nested pages -> listings
#   ../data/scraped/sources.json  -- source_id -> {source_name, tier}
#
# TODO: replace this stub with a jq invocation (or a short pipeline) that
# reads both files, flattens the nested listings, joins in each listing's
# tier via its page's source_id, groups by category, and prints the result.

set -euo pipefail

echo "not implemented" >&2
exit 1
