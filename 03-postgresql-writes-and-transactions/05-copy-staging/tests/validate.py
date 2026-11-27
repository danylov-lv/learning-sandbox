import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import re
from tempfile import TemporaryDirectory

from psycopg import errors, sql

from harness.checks import read_csv, require, require_prices, uses_copy, write_csv
from harness.db import arena
from harness.runner import run, submission

ROWS = (
    ("market", "c", 18, 3400), ("outlet", "a", 8, 850),
    ("market", "c", 11, 3250), ("market", "c", 18, 3400),
    ("direct", "d", 2, 1200),
)
TARGETS = ("observations", "current_prices")


def observe_merges(conn):
    conn.execute("""
        CREATE TEMP TABLE merge_writes (
            target text, affected_rows bigint, statement text
        ) ON COMMIT DELETE ROWS;
        CREATE FUNCTION record_merge_writes() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            INSERT INTO pg_temp.merge_writes
            SELECT TG_TABLE_NAME, count(*), current_query() FROM changed_rows;
            RETURN NULL;
        END;
        $$;
    """)
    for table in TARGETS:
        for operation in ("INSERT", "UPDATE"):
            conn.execute(sql.SQL("""
                CREATE TRIGGER {}
                AFTER {} ON {}
                REFERENCING NEW TABLE AS changed_rows
                FOR EACH STATEMENT EXECUTE FUNCTION record_merge_writes()
            """).format(
                sql.Identifier(f"observe_{operation.lower()}"),
                sql.SQL(operation),
                sql.Identifier(table),
            ))


def require_bulk_merges(conn, *, first_load):
    for table in TARGETS:
        writes = conn.execute("""
            SELECT affected_rows, statement
            FROM pg_temp.merge_writes
            WHERE target = %s AND affected_rows > 0
        """, (table,)).fetchall()
        require(
            all(re.search(r"\bprice_stage\b", statement, flags=re.I) for _, statement in writes),
            f"write rows into {table} from price_stage",
        )
        if first_load:
            require(
                any(affected_rows > 1 for affected_rows, _ in writes),
                f"write multiple rows into {table} in a single set-based statement",
            )


def check(source: Path) -> None:
    load_csv = submission(source).load_csv
    with TemporaryDirectory() as temp, arena() as database, database.connect() as conn, database.connect() as reader:
        observe_merges(conn)
        good = write_csv(Path(temp) / "incoming.csv", ROWS)
        late = write_csv(Path(temp) / "late.csv", [("market", "c", 10, 3300), ("outlet", "a", 9, 875)])
        bad = write_csv(Path(temp) / "malformed.csv", [("outlet", "a", 10, 900), ("direct", "d", 3, "broken")])
        for previous in ([], read_csv(good)):
            conn.activity.clear()
            with conn.transaction():
                load_csv(conn, good)
                require(uses_copy(conn), "stream the CSV into price_stage using COPY FROM STDIN")
                require_bulk_merges(conn, first_load=not previous)
                require_prices(conn, read_csv(good))
                require_prices(reader, previous)
            require_prices(reader, read_csv(good))

        expected = read_csv(good) + read_csv(late)
        with conn.transaction():
            load_csv(conn, late)
            require_bulk_merges(conn, first_load=False)
        require_prices(reader, expected)

        try:
            with conn.transaction():
                load_csv(conn, bad)
        except errors.InvalidTextRepresentation:
            pass
        else:
            raise AssertionError("propagate the malformed integer as a PostgreSQL error")
        require_prices(reader, expected)


if __name__ == "__main__":
    raise SystemExit(run(check, __file__))
