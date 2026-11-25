from collections.abc import Callable

from harness.db import Connection


def adjust_stock(
    conn: Connection,
    skus: tuple[str, str],
    delta: int,
    ordered: bool,
    after_first: Callable[[str], None],
) -> None:
    raise NotImplementedError
