"""Deterministic drill-day builder — GIVEN tooling, run it, don't rewrite it.

Derives data/raw/dt=2025-06-15/prices.ndjson from the committed generator
output for 2025-06-14:

  1. every line has its scraped_at date moved forward one day (textual
     "2025-06-14" -> "2025-06-15"; the date string occurs nowhere else in a
     record), so the file reads as a plausible scrape dump for 2025-06-15;
  2. every 10th line (0-based line index divisible by 10) is truncated to its
     first 30 characters, guaranteeing json.loads fails on it.

No randomness: two runs produce byte-identical output. The script then
classifies its own output with the same reference rules the validator uses
and prints the counts your DAG run on 2025-06-15 is expected to reproduce.

Run from the task directory:

    uv run python tests/make_drill_day.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _reference import classify_file  # noqa: E402
from harness.common import raw_day_file  # noqa: E402

SOURCE_DAY = "2025-06-14"
DRILL_DAY = "2025-06-15"
CORRUPT_EVERY = 10
TRUNCATE_AT = 30


def main():
    src = raw_day_file(SOURCE_DAY)
    if not src.exists():
        print(f"source file not found: {src} — run `uv run python generate.py` from the module root first")
        sys.exit(1)

    dst = raw_day_file(DRILL_DAY)
    dst.parent.mkdir(parents=True, exist_ok=True)

    out_lines = []
    for i, line in enumerate(src.read_text(encoding="utf-8").splitlines()):
        line = line.replace(SOURCE_DAY, DRILL_DAY)
        if i % CORRUPT_EVERY == 0:
            line = line[:TRUNCATE_AT]
        out_lines.append(line)

    dst.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    stats = classify_file(dst, DRILL_DAY)
    quarantined = stats["malformed"] + stats["invalid_total"]
    rate = quarantined / stats["total_lines"]

    print(f"wrote {dst}")
    print(f"total_lines:        {stats['total_lines']}")
    print(f"malformed:          {stats['malformed']}")
    print(f"invalid_total:      {stats['invalid_total']}")
    for reason, n in stats["invalid_by_reason"].items():
        print(f"  {reason}: {n}")
    print(f"valid (-> staging): {stats['valid']}")
    print(f"quarantine rate:    {rate:.4f} ({'ABOVE' if rate > 0.03 else 'below'} the 3% threshold)")


if __name__ == "__main__":
    main()
