from collections.abc import Sequence

from harness.db import Connection, Event


def apply_events(conn: Connection, events: Sequence[Event]) -> None:
    raise NotImplementedError
