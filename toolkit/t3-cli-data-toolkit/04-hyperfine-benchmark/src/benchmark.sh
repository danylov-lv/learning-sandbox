#!/usr/bin/env bash
# Run hyperfine comparing exactly two commands that both count the number
# of .log files under data/filetree/ -- one via `fd`, one via `rg`.
#
# Required flags: --warmup <N> and
#   --export-json 04-hyperfine-benchmark/results.json
# (path relative to the module root -- run this script from there).
#
# TODO: replace this stub with the hyperfine invocation.

set -euo pipefail

echo "not implemented" >&2
exit 1
