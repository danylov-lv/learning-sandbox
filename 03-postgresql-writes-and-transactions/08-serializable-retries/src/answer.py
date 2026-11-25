from collections.abc import Callable

from harness.db import Connection


def reserve(
    conn: Connection,
    worker: str,
    units: int,
    limit: int,
    isolation: str,
    max_attempts: int,
    after_read: Callable[[int, int], None],
) -> bool:
    raise NotImplementedError
