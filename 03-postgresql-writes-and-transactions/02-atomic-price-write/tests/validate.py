import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from psycopg.pq import TransactionStatus

from harness.checks import InjectedFailure, require, require_prices
from harness.db import Event, arena
from harness.runner import run, submission


def check(source: Path) -> None:
    record = submission(source).record
    for fail in (True, False):
        event = Event("market", "b", 13 if fail else 21, 1599 if fail else 1899)
        with arena() as database, database.connect() as conn, database.connect() as reader:
            calls = []

            def before_current():
                calls.append(True)
                require(conn.info.transaction_status == TransactionStatus.INTRANS, "write hook ran outside the transaction")
                actual = conn.execute("SELECT * FROM observations").fetchall()
                require(actual == [event], "write the observation before invoking the hook")
                require(conn.execute("SELECT * FROM current_prices").fetchall() == [], "invoke the hook before updating the current price")
                require_prices(reader, [])
                if fail:
                    raise InjectedFailure("failure between writes")

            try:
                record(conn, event, before_current)
            except InjectedFailure:
                require(fail, "unexpected injected failure")
            else:
                require(not fail, "propagate the injected failure")
            require(calls == [True], "invoke the write hook once")
            require(conn.info.transaction_status == TransactionStatus.IDLE, "leave the connection idle")
            require_prices(reader, [] if fail else [event])


if __name__ == "__main__":
    raise SystemExit(run(check, __file__))
