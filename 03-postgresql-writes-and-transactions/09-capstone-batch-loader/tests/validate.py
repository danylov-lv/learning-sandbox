import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from threading import Event

from psycopg import errors
from psycopg.pq import TransactionStatus

from harness.checks import (
    InjectedFailure,
    await_block,
    await_signal,
    read_csv,
    require,
    require_prices,
    uses_copy,
    write_csv,
)
from harness.db import arena
from harness.runner import run, submission

BATCH_A = (
    ("market", "a", 17, 1700), ("market", "a", 11, 1150),
    ("market", "a", 17, 1700), ("outlet", "b", 5, 500),
)
BATCH_B = (
    ("market", "a", 14, 1400), ("market", "a", 11, 1150),
    ("outlet", "b", 12, 1100), ("direct", "a", 2, 900),
)


def verify(conn, batches):
    registered = conn.execute("SELECT batch_id FROM processed_batches ORDER BY batch_id").fetchall()
    require(registered == [(name,) for name in sorted(batches)], "batch ledger differs from committed batches")
    require_prices(conn, [event for path in batches.values() for event in read_csv(path)])


def sequential(load_batch, good, bad):
    with arena() as database, database.connect() as conn, database.connect() as reader:
        calls = []

        def before_commit():
            calls.append(True)
            require(conn.info.transaction_status == TransactionStatus.INTRANS, "invoke the hook before commit")
            verify(conn, {"friday": good})
            verify(reader, {})
            if len(calls) == 1:
                raise InjectedFailure("pre-commit failure")

        try:
            load_batch(conn, "friday", good, before_commit)
        except InjectedFailure:
            pass
        else:
            raise AssertionError("propagate the failure before commit")
        require(calls == [True], "reach the first pre-commit checkpoint")
        require(conn.info.transaction_status == TransactionStatus.IDLE, "roll back the failed attempt")
        verify(reader, {})

        require(load_batch(conn, "friday", good, before_commit) is True, "a successful new batch must return True")
        require(calls == [True, True], "invoke the hook exactly once per newly applied batch")
        require(uses_copy(conn), "load new CSV rows via COPY FROM STDIN into price_stage")
        verify(reader, {"friday": good})
        require(load_batch(conn, "friday", good, before_commit) is False, "a committed batch must return False on replay")
        require(calls == [True, True], "skip the pre-commit hook on replay")

        try:
            load_batch(conn, "malformed", bad, before_commit)
        except errors.InvalidTextRepresentation:
            pass
        else:
            raise AssertionError("propagate a malformed CSV integer")
        verify(reader, {"friday": good})


def concurrent(load_batch, paths, same_batch):
    left_path, right_path = paths
    right_id = "left" if same_batch else "right"
    with (
        arena() as database,
        database.connect() as observer,
        database.connect() as left,
        database.connect() as right,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        first_ready = Event()
        release = Event()
        calls = []

        def pause_first():
            verify(left, {"left": left_path})
            verify(observer, {})
            first_ready.set()
            await_signal(release, "the validator did not release the first worker")

        first = pool.submit(load_batch, left, "left", left_path, pause_first)
        try:
            await_signal(first_ready, "first worker did not reach the pre-commit checkpoint")
            second = pool.submit(load_batch, right, right_id, right_path, lambda: calls.append(True))
            await_block(observer, right, left)
        finally:
            release.set()
        require(first.result() is True, "first worker must commit a new batch")
        require(second.result() is (not same_batch), "second worker must apply only a new batch")
        require(calls == ([] if same_batch else [True]), "invoke the hook only after applying a new batch")
        expected = {"left": left_path}
        if not same_batch:
            expected["right"] = right_path
        verify(observer, expected)


def check(source: Path, checkpoint: int = 2) -> None:
    load_batch = submission(source).load_batch
    with TemporaryDirectory() as temp:
        directory = Path(temp)
        left = write_csv(directory / "left.csv", BATCH_A)
        right = write_csv(directory / "right.csv", BATCH_B)
        bad = write_csv(directory / "malformed.csv", [("direct", "c", 5, 1100), ("outlet", "b", 13, "broken")])
        sequential(load_batch, left, bad)
        if checkpoint == 2:
            concurrent(load_batch, (left, right), same_batch=False)
            concurrent(load_batch, (left, left), same_batch=True)


if __name__ == "__main__":
    raise SystemExit(run(check, __file__, checkpoints=True))
