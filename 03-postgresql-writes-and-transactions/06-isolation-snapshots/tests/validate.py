import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from psycopg.pq import TransactionStatus

from harness.checks import require
from harness.db import arena
from harness.runner import run, submission


def check(source: Path) -> None:
    read_snapshots = submission(source).read_snapshots
    cases = (("read committed", "b", 37, 54), ("repeatable read", "a", 10, 48))
    for isolation, sku, start, changed in cases:
        with arena() as database, database.connect() as reader, database.connect() as writer:
            writer.execute("INSERT INTO stock VALUES (%s, %s), ('c', 390)", (sku, start))
            steps = []

            def after_read(step):
                steps.append(step)
                require(step == len(steps), "signal each of the three reads in order")
                require(reader.info.transaction_status == TransactionStatus.INTRANS, "keep one reader transaction open")
                actual = reader.execute("SHOW transaction_isolation").fetchone()[0]
                require(actual == isolation, f"expected reader isolation {isolation}, got {actual}")
                if step == 1:
                    writer.execute("BEGIN")
                    writer.execute("UPDATE stock SET quantity = %s WHERE sku = %s", (changed, sku))
                if step == 2:
                    writer.execute("COMMIT")

            snapshots = read_snapshots(reader, isolation, sku, after_read)
            expected = (start, start, changed if isolation == "read committed" else start)
            require(steps == [1, 2, 3], "perform all three reads")
            require(snapshots == expected, f"expected snapshot quantities {expected}, got {snapshots}")
            require(reader.info.transaction_status == TransactionStatus.IDLE, "close the reader transaction")
            actual = reader.execute("SELECT quantity FROM stock WHERE sku = %s", (sku,)).fetchone()
            require(actual == (changed,), "a fresh read must see the committed writer value")


if __name__ == "__main__":
    raise SystemExit(run(check, __file__))
