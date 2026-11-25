from collections.abc import Callable

from harness.db import Connection


def read_snapshots(
    reader: Connection,
    isolation: str,
    sku: str,
    after_read: Callable[[int], None],
) -> tuple[int, int, int]:
    raise NotImplementedError
