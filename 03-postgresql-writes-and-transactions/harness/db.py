import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent
Key = tuple[str, str]


class Event(NamedTuple):
    source: str
    sku: str
    version: int
    cents: int


class ObservedCursor(psycopg.Cursor):
    def _record(self, operation, query):
        if isinstance(query, sql.Composable):
            query = query.as_string(self)
        elif isinstance(query, bytes):
            query = query.decode("utf-8")
        self.connection.activity.append((operation, query))

    def execute(self, query, params=None, **kwargs):
        result = super().execute(query, params, **kwargs)
        self._record("execute", query)
        return result

    def executemany(self, query, params_seq, **kwargs):
        result = super().executemany(query, params_seq, **kwargs)
        self._record("execute", query)
        return result

    @contextmanager
    def copy(self, statement, params=None, **kwargs):
        with super().copy(statement, params, **kwargs) as copy:
            self._record("copy", statement)
            yield copy


class Connection(psycopg.Connection):
    activity: list[tuple[str, str]]


def create_staging_table(conn: Connection) -> None:
    conn.execute("""
        CREATE TEMP TABLE price_stage (
            source text NOT NULL,
            sku text NOT NULL,
            version integer NOT NULL CHECK (version > 0),
            cents integer NOT NULL CHECK (cents > 0)
        ) ON COMMIT DROP
    """)


class Database:
    def __init__(self, schema: str):
        self.schema = schema

    def connect(self) -> Connection:
        connection = Connection.connect(
            host="127.0.0.1",
            port=os.environ.get("SANDBOX_03_WRITES_PORT", "54321"),
            dbname="sandbox",
            user="sandbox",
            password="sandbox",
            autocommit=True,
            connect_timeout=5,
            cursor_factory=ObservedCursor,
        )
        connection.activity = []
        try:
            connection.execute(
                sql.SQL("SET search_path TO {}, public").format(sql.Identifier(self.schema))
            )
            connection.execute("SET statement_timeout TO '15s'")
        except BaseException:
            connection.close()
            raise
        return connection

    def initialize(self) -> None:
        with self.connect() as conn, conn.transaction():
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
            conn.execute((ROOT / "seed/schema.sql").read_text(encoding="utf-8"))


@contextmanager
def arena() -> Iterator[Database]:
    database = Database(f"writes_{uuid4().hex}")
    database.initialize()
    try:
        yield database
    finally:
        with database.connect() as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(database.schema)))
