"""Prefect port of the incremental price-record loader.

Run directly (no Prefect server needed — Prefect 3 uses an ephemeral local
API by default for a script run this way):

    uv run python src/flow.py --date 2025-06-03

Optional: run `prefect server start` in another terminal first (default UI
port 4200) to watch flow/task runs in the UI while iterating. Not required
for grading or for normal use.
"""

import argparse

from prefect import flow, task


# TODO: @task with retries configured (retries=..., retry_delay_seconds=...).
# Read data/raw/dt=<date>/prices.ndjson (see harness.common.raw_day_file) and
# return its lines (or an iterator over them) for the parse step.
def read_day_file(dt: str):
    raise NotImplementedError


# TODO: @task. Parse each line as JSON. Lines that fail json.loads are
# skipped (malformed/poison lines — not stored). Return one (line_no,
# payload) pair per line that parses successfully, 0-indexed or 1-indexed —
# just be consistent with what you load.
def parse_lines(lines):
    raise NotImplementedError


# TODO: @task with retries configured. Idempotently upsert each parsed
# record into staging.price_records_raw(dt, line_no, payload, loaded_at) on
# the module 06 warehouse (localhost:54306, db pipelines, sandbox/sandbox).
# Keyed on (dt, line_no) — running this twice for the same day must not
# change the row count. Return the number of rows loaded.
def load_records(dt: str, parsed_records):
    raise NotImplementedError


# TODO: @task. Insert one row into ops.load_audit with
# dag_id='prefect:incremental_load', a run_id you generate or pull from the
# Prefect run context, the target dt, rows_loaded, status, and finished_at.
def write_audit_row(dt: str, run_id: str, rows_loaded: int, status: str):
    raise NotImplementedError


@flow(name="incremental-load")
def incremental_load(dt: str):
    # TODO: wire the tasks above together and return/log a summary.
    raise NotImplementedError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()
    incremental_load(args.date)


if __name__ == "__main__":
    main()
