"""Convert PriceWatch raw JSONL snapshots into a single Parquet file.

Contract
--------
    convert(raw_dir, out_path) -> int

- `raw_dir`: directory containing `part-*.jsonl` (each line one JSON object,
  see the row schema in the module README / generate.py).
- `out_path`: path to write, e.g. `data/formats/snapshots.parquet`. Write a
  single Parquet file (not a dataset directory).
- Returns the number of rows written.

Output columns, in this exact order and type:

    product_id      int64
    source_id       int64
    url             string
    title           string
    category        string
    brand           string
    price           float64, nullable
    currency        string
    in_stock        bool, nullable
    captured_at     timestamp[us, tz=UTC]
    attrs           string  (the nested `attrs` dict re-serialized as JSON text)
    scrape_run_id   string
    http_status     int64

Notes
-----
- The raw JSON has no schema of its own — `json.loads` gives you Python
  ints/floats/str/bool/None/dict per line. You choose the Arrow types when
  you build each batch; get them right (esp. `captured_at` as a real UTC
  timestamp column, not a string).
- Non-200 rows carry `price: null` and `in_stock: null` in the source data.
  Preserve those as nulls in the output — never coerce to 0 / False.
- Streaming requirement: read and write in bounded-size chunks. The process
  must not hold the whole dataset (or the whole output) in memory at once.
  Peak RSS should stay well under ~4 GB regardless of how large `raw_dir` is.
  A `json.load`-the-whole-file (or pandas.read_json-the-whole-thing) approach
  is a fail even if the resulting file is byte-correct.
- `attrs` arrives as a JSON object; store it back out as a JSON string column
  (not as a struct/map column) — that's what the README's column contract
  wants for this task.
"""


def convert(raw_dir, out_path):
    raise NotImplementedError("implement Parquet conversion")
