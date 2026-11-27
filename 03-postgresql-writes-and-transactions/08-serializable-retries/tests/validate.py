import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from psycopg import errors
from psycopg.pq import TransactionStatus

from harness.checks import WAIT_SECONDS, advisory_gate, await_block, require
from harness.db import arena
from harness.runner import run, submission


def serializable_attempts(reader, winner, loser, start_attempts):
    reader.execute("""
        CREATE FUNCTION pause_allocation_update() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM pg_advisory_xact_lock(current_setting('writes.reserve_gate')::bigint);
            RETURN NULL;
        END;
        $$;
        CREATE TRIGGER pause_allocation_update AFTER UPDATE ON allocations
        FOR EACH STATEMENT EXECUTE FUNCTION pause_allocation_update();
    """)
    with advisory_gate(reader) as loser_gate:
        with advisory_gate(reader) as winner_gate:
            for conn, gate in ((winner, winner_gate), (loser, loser_gate)):
                conn.execute("SELECT set_config('writes.reserve_gate', %s, false)", (str(gate),))
            first, second = start_attempts()
            await_block(reader, winner, reader)
            await_block(reader, loser, reader)
        # Finish the winner's commit before the loser's UPDATE can return.
        winning_trace = first.result()
    return winning_trace, second.result()


def check(source: Path) -> None:
    reserve = submission(source).reserve
    for isolation, max_attempts in (("repeatable read", 2), ("serializable", 2), ("serializable", 1)):
        with (
            arena() as database,
            database.connect() as reader,
            database.connect() as winner,
            database.connect() as loser,
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            reader.execute("INSERT INTO allocations VALUES ('worker-a', 0), ('worker-b', 0)")
            first_reads = Barrier(2, timeout=WAIT_SECONDS)

            def attempt(conn, worker):
                reads = []

                def after_read(attempt_number, total):
                    require(conn.info.transaction_status == TransactionStatus.INTRANS, "read the quota within a transaction")
                    actual = conn.execute("SHOW transaction_isolation").fetchone()[0]
                    require(actual == isolation, f"expected {isolation}, got {actual}")
                    reads.append((attempt_number, total))
                    if attempt_number == 1:
                        first_reads.wait()

                try:
                    result = reserve(conn, worker, 6, 10, isolation, max_attempts, after_read)
                    require(isinstance(result, bool), "return whether this allocation was granted")
                except errors.SerializationFailure as error:
                    result = error.sqlstate
                require(conn.info.transaction_status == TransactionStatus.IDLE, "finish or roll back every attempt")
                return result, tuple(reads)

            def start_attempts():
                return pool.submit(attempt, winner, "worker-a"), pool.submit(attempt, loser, "worker-b")

            if isolation == "serializable":
                traces = set(serializable_attempts(reader, winner, loser, start_attempts))
            else:
                traces = {job.result() for job in start_attempts()}
            total = reader.execute("SELECT sum(units) FROM allocations").fetchone()[0]

            if isolation == "repeatable read":
                require(traces == {(True, ((1, 0),))} and total == 12, "reproduce write skew under REPEATABLE READ")
            elif max_attempts == 2:
                expected = {(True, ((1, 0),)), (False, ((1, 0), (2, 6)))}
                require(traces == expected and total == 6, "retry the losing transaction from its first read")
            else:
                expected = {(True, ((1, 0),)), ("40001", ((1, 0),))}
                require(traces == expected and total == 6, "propagate 40001 when the attempt budget is exhausted")

    with arena() as database, database.connect() as conn:
        conn.execute("INSERT INTO allocations VALUES ('worker-a', 2), ('worker-b', 3)")
        require(
            reserve(conn, "worker-a", 3, 8, "serializable", 2, lambda attempt, total: None) is True,
            "allow a reservation that exactly reaches the limit",
        )
        rows = conn.execute("SELECT worker, units FROM allocations ORDER BY worker").fetchall()
        require(rows == [("worker-a", 5), ("worker-b", 3)], "increment the existing allocation")

        attempts = []

        def fail(attempt_number, total):
            attempts.append(attempt_number)
            conn.execute("UPDATE allocations SET units = -1 WHERE worker = 'worker-a'")

        try:
            reserve(conn, "worker-a", 6, 10, "serializable", 2, fail)
        except errors.CheckViolation:
            pass
        else:
            raise AssertionError("propagate an unrelated constraint error")
        require(attempts == [1], "retry only serialization failures in this exercise")


if __name__ == "__main__":
    raise SystemExit(run(check, __file__))
