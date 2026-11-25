import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import re
from tempfile import TemporaryDirectory

from psycopg import errors

from harness.checks import read_csv, require, require_prices, uses_copy, write_csv
from harness.db import arena
from harness.runner import run, submission

ROWS = (
    ("market", "c", 18, 3400), ("outlet", "a", 8, 850),
    ("market", "c", 11, 3250), ("market", "c", 18, 3400),
    ("direct", "d", 2, 1200),
)


def check(source: Path) -> None:
    load_csv = submission(source).load_csv
    with TemporaryDirectory() as temp, arena() as database, database.connect() as conn, database.connect() as reader:
        good = write_csv(Path(temp) / "incoming.csv", ROWS)
        late = write_csv(Path(temp) / "late.csv", [("market", "c", 10, 3300), ("outlet", "a", 9, 875)])
        bad = write_csv(Path(temp) / "malformed.csv", [("outlet", "a", 10, 900), ("direct", "d", 3, "broken")])
        for previous in ([], read_csv(good)):
            conn.activity.clear()
            with conn.transaction():
                load_csv(conn, good)
                require(uses_copy(conn), "stream the CSV into price_stage using COPY FROM STDIN")
                statements = [
                    statement.lower().replace('"', "")
                    for operation, statement in conn.activity
                    if operation == "execute"
                ]
                for table in ("observations", "current_prices"):
                    require(
                        any(
                            re.search(rf"\binsert\s+into\s+{table}\b", statement)
                            and re.search(r"\bselect\b", statement)
                            and "price_stage" in statement
                            for statement in statements
                        ),
                        f"merge price_stage into {table} as a set",
                    )
                require_prices(conn, read_csv(good))
                require_prices(reader, previous)
            require_prices(reader, read_csv(good))

        expected = read_csv(good) + read_csv(late)
        with conn.transaction():
            load_csv(conn, late)
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
