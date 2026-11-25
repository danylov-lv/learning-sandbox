from collections.abc import Callable
from pathlib import Path

from harness.db import Connection


def load_batch(
    conn: Connection,
    batch_id: str,
    path: Path,
    before_commit: Callable[[], None],
) -> bool:
    raise NotImplementedError
