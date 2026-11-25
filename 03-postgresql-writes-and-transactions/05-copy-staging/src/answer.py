from pathlib import Path

from harness.db import Connection


def load_csv(conn: Connection, path: Path) -> None:
    raise NotImplementedError
