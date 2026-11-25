import csv
from collections.abc import Iterable
from pathlib import Path
from threading import Event as Signal
from time import monotonic

from harness.db import Connection, Event

FIELDS = Event._fields
WAIT_SECONDS = 8


class InjectedFailure(Exception):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def await_signal(signal: Signal, message: str) -> None:
    require(signal.wait(WAIT_SECONDS), message)


def await_block(observer: Connection, blocked: Connection, blocker: Connection) -> None:
    until = monotonic() + WAIT_SECONDS
    delay = Signal()
    while monotonic() < until:
        blocking = observer.execute(
            "SELECT pg_blocking_pids(%s)", (blocked.info.backend_pid,)
        ).fetchone()[0]
        if blocker.info.backend_pid in blocking:
            return
        delay.wait(0.025)
    raise AssertionError("expected PostgreSQL to report one worker blocked by the other")


def write_csv(path: Path, rows: Iterable[tuple]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(FIELDS)
        writer.writerows(rows)
    return path


def read_csv(path: Path) -> list[Event]:
    with path.open(encoding="utf-8", newline="") as stream:
        return [
            Event(row["source"], row["sku"], int(row["version"]), int(row["cents"]))
            for row in csv.DictReader(stream)
        ]


def require_prices(conn: Connection, events: Iterable[Event]) -> None:
    history = set(events)
    latest: dict[tuple[str, str], Event] = {}
    for row in sorted(history, key=lambda event: event.version):
        latest[row.source, row.sku] = row
    actual_history = conn.execute("SELECT source, sku, version, cents FROM observations").fetchall()
    require(sorted(actual_history) == sorted(history), "price history differs from expected events")
    actual_current = conn.execute("SELECT source, sku, version, cents FROM current_prices").fetchall()
    require(sorted(actual_current) == sorted(latest.values()), "current prices differ from the latest events")


def uses_copy(conn: Connection) -> bool:
    return any(
        operation == "copy"
        and "price_stage" in statement.lower()
        and "from stdin" in " ".join(statement.lower().split())
        for operation, statement in conn.activity
    )
