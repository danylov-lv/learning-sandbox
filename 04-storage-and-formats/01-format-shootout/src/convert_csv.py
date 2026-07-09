"""Convert PriceWatch raw JSONL snapshots into a single CSV file.

Contract
--------
    convert(raw_dir, out_path) -> int

- `raw_dir`: directory containing `part-*.jsonl` (each line one JSON object,
  see the row schema in the module README / generate.py).
- `out_path`: path to write, e.g. `data/formats/snapshots.csv`. One CSV file,
  header row included.
- Returns the number of rows written.

Output columns, in this exact order (same order as the Parquet converter):

    product_id, source_id, url, title, category, brand, price, currency,
    in_stock, captured_at, attrs, scrape_run_id, http_status

- `captured_at`: write the ISO-8601 string as-is (CSV has no timestamp type,
  don't reformat it).
- `attrs`: the nested dict re-serialized as a single JSON-string field (a
  CSV cell, so it needs correct quoting/escaping if it contains commas or
  quotes — let your CSV writer handle that, don't hand-roll it).
- Nulls: non-200 rows have `price` and `in_stock` null in the source. They
  must show up as an empty field in the CSV, not the literal text "None",
  "null", "0", or "False".

Streaming requirement: read and write in bounded-size chunks/rows, never
load the whole dataset into memory (no giant list-of-dicts, no
pandas.read_json/to_csv on the full file). Peak RSS should stay well under
~4 GB regardless of dataset size.
"""


def convert(raw_dir, out_path):
    raise NotImplementedError("implement CSV conversion")
