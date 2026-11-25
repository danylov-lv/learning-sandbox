from collections.abc import Sequence

from harness.db import Connection, Key


def import_notes(conn: Connection, notes: Sequence[tuple[str, str, str]]) -> list[Key]:
    raise NotImplementedError
