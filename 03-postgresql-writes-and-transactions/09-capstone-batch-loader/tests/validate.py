import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from threading import Event

from psycopg import errors, sql
from psycopg.pq import TransactionStatus

from harness.checks import (
    InjectedFailure,
    advisory_gate,
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


def with_copy_check(load_batch):
    def checked_load(conn, batch_id, path, before_commit):
        start = len(conn.activity)
        message = "load this batch via COPY FROM STDIN into price_stage"
        try:
            applied = load_batch(conn, batch_id, path, before_commit)
        except (InjectedFailure, errors.InvalidTextRepresentation):
            require(uses_copy(conn, since=start), message)
            raise
        if applied is True:
            require(uses_copy(conn, since=start), message)
        return applied

    return checked_load


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


def concurrent(load_batch, paths, same_batch, *, roll_back_first=False):
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
            if roll_back_first:
                raise InjectedFailure("roll back while the other worker waits")

        first = pool.submit(load_batch, left, "left", left_path, pause_first)
        try:
            await_signal(first_ready, "first worker did not reach the pre-commit checkpoint")
            second = pool.submit(load_batch, right, right_id, right_path, lambda: calls.append(True))
            await_block(observer, right, left)
        finally:
            release.set()
        try:
            first_applied = first.result()
        except InjectedFailure:
            require(roll_back_first, "unexpected pre-commit failure")
            expected = {}
        else:
            require(not roll_back_first and first_applied is True, "finish the first worker as requested")
            expected = {"left": left_path}

        second_applies = roll_back_first or not same_batch
        require(second.result() is second_applies, "apply the waiting batch only if its ID has not committed")
        require(calls == ([True] if second_applies else []), "invoke the hook only after applying a new batch")
        if second_applies:
            expected[right_id] = right_path
        verify(observer, expected)


def overlapping_merges(load_batch, left_path, right_path, *, target):
    with (
        arena() as database,
        database.connect() as observer,
        database.connect() as left,
        database.connect() as right,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        observer.execute("""
            CREATE FUNCTION pause_second_merge_key() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE
                gate text := current_setting('writes.merge_gate', true);
                first_key text := nullif(current_setting('writes.first_merge_key', true), '');
                merge_key text := json_build_array(
                    NEW.source, NEW.sku, CASE WHEN TG_TABLE_NAME = 'observations' THEN NEW.version END
                )::text;
            BEGIN
                IF gate IS NULL THEN
                    RETURN NEW;
                END IF;
                IF first_key IS NULL THEN
                    PERFORM set_config('writes.first_merge_key', merge_key, true);
                ELSIF merge_key <> first_key THEN
                    PERFORM pg_advisory_xact_lock(gate::bigint);
                END IF;
                RETURN NEW;
            END;
            $$;
        """)
        observer.execute(sql.SQL("""
            CREATE TRIGGER pause_merge BEFORE INSERT ON {}
            FOR EACH ROW EXECUTE FUNCTION pause_second_merge_key()
        """).format(sql.Identifier(target)))
        with advisory_gate(observer) as gate:
            left.execute("SELECT set_config('writes.merge_gate', %s, false)", (str(gate),))
            first = pool.submit(load_batch, left, "left", left_path, lambda: None)
            await_block(observer, left, observer)
            second = pool.submit(load_batch, right, "right", right_path, lambda: None)
            await_block(observer, right, left)
        try:
            require(first.result() is True, "commit the first overlapping batch")
            require(second.result() is True, "commit the second overlapping batch")
        except errors.DeadlockDetected as error:
            raise AssertionError(f"overlapping writes to {target} deadlocked (SQLSTATE {error.sqlstate})") from error
        verify(observer, {"left": left_path, "right": right_path})


def check(source: Path, checkpoint: int = 2) -> None:
    load_batch = with_copy_check(submission(source).load_batch)
    with TemporaryDirectory() as temp:
        directory = Path(temp)
        left = write_csv(directory / "left.csv", BATCH_A)
        right = write_csv(directory / "right.csv", BATCH_B)
        bad = write_csv(directory / "malformed.csv", [("direct", "c", 5, 1100), ("outlet", "b", 13, "broken")])
        sequential(load_batch, left, bad)
        if checkpoint == 2:
            concurrent(load_batch, (left, right), same_batch=False)
            concurrent(load_batch, (left, left), same_batch=True)
            concurrent(load_batch, (left, left), same_batch=True, roll_back_first=True)
            merge_left = write_csv(directory / "merge-left.csv", [("market", "a", 1, 100), ("market", "b", 1, 200)])
            merge_right = write_csv(directory / "merge-right.csv", [("market", "b", 2, 240), ("market", "a", 2, 160)])
            overlapping_merges(load_batch, merge_left, merge_right, target="current_prices")

            shared = [("market", "a", 1, 100), ("market", "a", 2, 200)]
            history_left = write_csv(directory / "history-left.csv", shared)
            history_right = write_csv(directory / "history-right.csv", reversed(shared))
            overlapping_merges(load_batch, history_left, history_right, target="observations")


if __name__ == "__main__":
    raise SystemExit(run(check, __file__, checkpoints=True))
