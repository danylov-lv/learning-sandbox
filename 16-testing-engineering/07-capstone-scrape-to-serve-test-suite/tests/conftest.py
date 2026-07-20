"""GIVEN scaffolding -- real Postgres and Redis containers for your tests.

This is not the deliverable; `test_unit.py`, `test_integration.py`, and
`test_contract.py` are. You should not need to edit this file. It exists
to save you the container-lifecycle boilerplate so you can focus on
writing assertions against `CatalogRepo`, `ProductCache`, and the API
built by `make_app`.

Session-scoped (one real container for the whole `pytest` run, so a
mutant-grading run -- one fresh `python -m pytest` subprocess per mutant --
pays the container-startup cost only once per subprocess):

  - `postgres_dsn` -- a `postgres:16` container's connection URL.
  - `redis_url` -- a `redis:7` container's connection URL.

Function-scoped (fresh state for every single test, even though the
containers themselves are shared):

  - `conn` -- a `psycopg` connection against the Postgres container, with
    the `products` table dropped and recreated before the test runs.
  - `repo` -- a `CatalogRepo` wrapping that same `conn`.
  - `redis_client` -- a `redis-py` client against the Redis container,
    flushed (`FLUSHDB`) before the test runs.
  - `cache` -- a `ProductCache` wrapping that same `redis_client`.
  - `app` / `client` -- a FastAPI app built via `make_app(repo, cache)`,
    wrapped in a `fastapi.testclient.TestClient`, for contract tests
    against the running ASGI app rather than calling `repo`/`cache`
    methods directly.

`test_unit.py` does not need any of these fixtures at all -- the
parser/normalize layer is pure and needs no container.
"""

from __future__ import annotations

import psycopg
import pytest
import redis
from fastapi.testclient import TestClient
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from src.sut import CatalogRepo, ProductCache, make_app


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    with PostgresContainer("postgres:16") as container:
        yield container.get_connection_url(driver=None)


@pytest.fixture(scope="session")
def redis_url() -> str:
    with RedisContainer("redis:7") as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest.fixture()
def conn(postgres_dsn: str):
    connection = psycopg.connect(postgres_dsn)
    try:
        with connection.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS products")
        connection.commit()
        CatalogRepo(connection).create_schema()
        yield connection
    finally:
        connection.close()


@pytest.fixture()
def repo(conn) -> CatalogRepo:
    return CatalogRepo(conn)


@pytest.fixture()
def redis_client(redis_url: str):
    client = redis.Redis.from_url(redis_url)
    try:
        client.flushdb()
        yield client
    finally:
        client.close()


@pytest.fixture()
def cache(redis_client) -> ProductCache:
    return ProductCache(redis_client)


@pytest.fixture()
def app(repo: CatalogRepo, cache: ProductCache):
    return make_app(repo, cache)


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client
