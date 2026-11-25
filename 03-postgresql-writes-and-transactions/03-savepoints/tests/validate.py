import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from psycopg import errors

from harness.checks import require
from harness.db import arena
from harness.runner import run, submission


def note_rows(conn):
    return conn.execute("SELECT source, sku, body FROM source_notes ORDER BY source, sku").fetchall()


def check(source: Path) -> None:
    import_notes = submission(source).import_notes
    existing = ("market", "b", "original")
    first = ("market", "a", "shipping confirmed")
    duplicate = ("market", "b", "overwrite")
    blank = ("market", "c", "")
    last = ("outlet", "d", "manual quote")
    with arena() as database, database.connect() as conn, database.connect() as reader:
        conn.execute("INSERT INTO source_notes VALUES (%s, %s, %s)", existing)
        conn.execute("""
            CREATE FUNCTION log_note_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE NOTICE 'note attempt %/%', NEW.source, NEW.sku;
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER log_note_attempt BEFORE INSERT ON source_notes
                FOR EACH ROW EXECUTE FUNCTION log_note_attempt();
        """)
        notices = []
        conn.add_notice_handler(lambda diagnostic: notices.append(diagnostic.message_primary))
        with conn.transaction():
            outer = conn.execute("SELECT txid_current()").fetchone()[0]
            rejected = import_notes(conn, [first, duplicate, blank, last])
            require(rejected == [duplicate[:2], blank[:2]], "report both rejected keys in input order")
            require(conn.execute("SELECT txid_current()").fetchone()[0] == outer, "keep the caller's transaction")
            require(
                notices == [f"note attempt {note[0]}/{note[1]}" for note in (first, duplicate, blank, last)],
                "attempt all four rows against PostgreSQL",
            )
            require(note_rows(conn) == sorted([existing, first, last]), "recover and retain both valid notes")
            require(note_rows(reader) == [existing], "the caller must control the commit")
        require(note_rows(reader) == sorted([existing, first, last]), "the caller's commit must publish the valid notes")
        try:
            with conn.transaction():
                import_notes(conn, [("absent", "a", "unknown offer")])
        except errors.ForeignKeyViolation:
            pass
        else:
            raise AssertionError("propagate unexpected foreign-key failures")


if __name__ == "__main__":
    raise SystemExit(run(check, __file__))
