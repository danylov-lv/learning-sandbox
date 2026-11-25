from collections.abc import Callable

from harness.db import Connection, Event


def record(conn: Connection, event: Event, before_current: Callable[[], None]) -> None:
    raise NotImplementedError
