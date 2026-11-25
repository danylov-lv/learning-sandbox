import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from psycopg import errors

from harness.checks import require
from harness.db import arena
from harness.runner import run


def check(source: Path) -> None:
    statements = {}
    for name in ("insert", "update", "delete"):
        statement = (source / f"{name}.sql").read_text(encoding="utf-8")
        if not any(line.strip() and not line.lstrip().startswith("--") for line in statement.splitlines()):
            raise NotImplementedError
        statements[name] = statement

    cases = (
        (
            ("market", "b", 9, 1799),
            [("market", "b", 10, 1999), ("outlet", "b", 9, 2199), ("market", "a", 9, 3000)],
        ),
        (
            ("direct", "c", 18, 890),
            [("direct", "c", 19, 970), ("market", "c", 18, 1000), ("direct", "d", 18, 1800)],
        ),
    )
    for target, seeds in cases:
        source_id, sku, version, cents = target
        params = dict(source=source_id, sku=sku, version=version, cents=cents)
        with arena() as database, database.connect() as conn:
            for row in seeds:
                conn.execute("INSERT INTO observations VALUES (%s, %s, %s, %s)", row)

            def expect_rows(expected):
                rows = conn.execute("SELECT source, sku, version, cents FROM observations").fetchall()
                require(sorted(rows) == sorted(expected), "a DML statement changed the wrong rows")

            result = conn.execute(statements["insert"], params).fetchall()
            require(result == [target], "INSERT must return the inserted row")
            expect_rows(seeds + [target])

            corrected = (*target[:3], cents + 73)
            result = conn.execute(statements["update"], {**params, "cents": corrected[3]}).fetchall()
            require(result == [corrected], "UPDATE must return the row with its new price")
            expect_rows(seeds + [corrected])

            negative = {**params, "version": version + 2, "cents": -1}
            try:
                conn.execute(statements["insert"], negative)
            except errors.CheckViolation:
                pass
            else:
                raise AssertionError("INSERT must expose a rejected price to its caller")
            expect_rows(seeds + [corrected])

            result = conn.execute(statements["delete"], params).fetchall()
            require(result == [corrected], "DELETE must return the deleted row")
            expect_rows(seeds)
            result = conn.execute(statements["delete"], params).fetchall()
            require(result == [], "missing target must return zero rows")
            expect_rows(seeds)


if __name__ == "__main__":
    raise SystemExit(run(check, __file__))
