"""GIVEN scaffolding -- a real Redis container for your tests to use.

This is not the deliverable; `test_redis_component.py` is. You should not
need to edit this file. It exists to save you the container-lifecycle
boilerplate so you can focus on writing assertions against `RateLimiter`
and `DedupFilter`.

- `redis_client` is session-scoped: one real `redis:7` container is started
  for the whole `pytest` run (this is what makes a mutant grading run --
  one fresh `python -m pytest` subprocess per mutant -- pay the
  container-startup cost only once per subprocess, not once per test).
- `flush_redis` is function-scoped and autouse: it flushes the whole
  container's keyspace before every test, so each test starts from an
  empty database even though the container itself is shared. (There is
  nothing else in this container, so a flush is safe and simpler than
  scoping deletes to a prefix.)
"""

from __future__ import annotations

import pytest
import redis
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def redis_client():
    with RedisContainer("redis:7") as container:
        client = container.get_client(decode_responses=True)
        yield client


@pytest.fixture(autouse=True)
def flush_redis(redis_client: redis.Redis):
    redis_client.flushdb()
    yield
