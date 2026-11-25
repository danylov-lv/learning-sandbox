import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from psycopg import errors
from psycopg.pq import TransactionStatus

from harness.checks import WAIT_SECONDS, await_block, await_signal, require
from harness.db import arena
from harness.runner import run, submission


def quantities(conn):
    return conn.execute("SELECT quantity FROM stock ORDER BY sku").fetchall()


def check(source: Path) -> None:
    adjust_stock = submission(source).adjust_stock

    def adjust(conn, keys, ordered, paused):
        def after_first(key):
            require(conn.info.transaction_status == TransactionStatus.INTRANS, "hold the first lock in a transaction")
            require(any(
                "for update" in " ".join(statement.lower().split())
                for operation, statement in conn.activity
                if operation == "execute"
            ), "acquire the row lock explicitly before invoking the hook")
            paused(key)

        adjust_stock(conn, keys, 7, ordered, after_first)

    for ordered in (False, True):
        with (
            arena() as database,
            database.connect() as reader,
            database.connect() as left,
            database.connect() as right,
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            reader.execute("INSERT INTO stock VALUES ('a', 100), ('b', 150)")
            if not ordered:
                both_locked = Barrier(2, timeout=WAIT_SECONDS)

                def pause(key, expected):
                    require(key == expected, "reproduce the caller's conflicting lock order")
                    both_locked.wait()

                jobs = (
                    pool.submit(adjust, left, ("a", "b"), False, lambda key: pause(key, "a")),
                    pool.submit(adjust, right, ("b", "a"), False, lambda key: pause(key, "b")),
                )
                victims = 0
                for job in jobs:
                    try:
                        job.result()
                    except errors.DeadlockDetected:
                        victims += 1
                require(victims == 1, "reproduce exactly one PostgreSQL deadlock")
                require(quantities(reader) == [(107,), (157,)], "only the survivor may commit")
                continue

            first_locked = Event()
            release = Event()

            def pause_first(key):
                require(key == "a", "take row locks in ascending SKU order")
                first_locked.set()
                await_signal(release, "the validator did not release the first worker")

            def check_second(key):
                require(key == "a", "use the same first lock for both input orders")

            first = pool.submit(adjust, left, ("b", "a"), True, pause_first)
            try:
                await_signal(first_locked, "first worker did not acquire its first lock")
                second = pool.submit(adjust, right, ("a", "b"), True, check_second)
                await_block(reader, right, left)
            finally:
                release.set()
            first.result()
            second.result()
            require(quantities(reader) == [(114,), (164,)], "both ordered operations must commit once")


if __name__ == "__main__":
    raise SystemExit(run(check, __file__))
