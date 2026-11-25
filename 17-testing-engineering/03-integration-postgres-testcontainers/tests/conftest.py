"""GIVEN scaffolding -- a real Postgres container for your tests to use.

This is not the deliverable; `test_repo.py` is. You should not need to
edit this file. It exists to save you the container-lifecycle boilerplate
so you can focus on writing assertions against `PriceRepo`.

- `postgres_dsn` is session-scoped: one real `postgres:16` container is
  started for the whole `pytest` run (this is what makes a mutant grading
  run -- one fresh `python -m pytest` subprocess per mutant -- pay the
  container-startup cost only once per subprocess, not once per test).
- `conn` is function-scoped: it opens a fresh `psycopg` connection against
  that same container for every test, drops and recreates the
  `observations` table first, and closes the connection afterward. Each
  test therefore starts from an empty table, even though the container
  itself is shared.
"""

from __future__ import annotations

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

from src.sut import PriceRepo


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    with PostgresContainer("postgres:16") as container:
        yield container.get_connection_url(driver=None)


@pytest.fixture()
def conn(postgres_dsn: str):
    connection = psycopg.connect(postgres_dsn)
    try:
        with connection.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS observations")
        connection.commit()
        PriceRepo.create_schema(connection)
        yield connection
    finally:
        connection.close()
