import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import re

from harness.checks import require, require_prices
from harness.db import Event, arena
from harness.runner import run, submission


IDENTIFIER = r'(?:"(?:[^"]|"")*"|[\w$]+)'


def check(source: Path) -> None:
    apply_events = submission(source).apply_events
    new = Event("market", "a", 15, 1500)
    old = Event("market", "a", 12, 1600)
    neighbor = Event("outlet", "a", 30, 1550)
    other = Event("market", "b", 1, 1799)
    for groups in (([new, neighbor], [old, new, other, old]), ([old, other], [neighbor, new, new])):
        with arena() as database, database.connect() as conn, database.connect() as reader:
            expected = []
            for events in groups:
                with conn.transaction():
                    apply_events(conn, events)
                    require_prices(reader, expected)
                expected.extend(events)
                require_prices(reader, expected)
            statements = [statement for action, statement in conn.activity if action == "execute"]
            for name in ("observations", "current_prices"):
                target = rf'(?:{IDENTIFIER}\s*\.\s*)?(?:"{name}"|{name}\b)'
                matching = rf'\binsert\s+into\s+{target}[\s\S]*\bon\s+conflict\b'
                require(
                    any(re.search(matching, statement, flags=re.I) for statement in statements),
                    f"exercise ON CONFLICT when inserting into {name}",
                )


if __name__ == "__main__":
    raise SystemExit(run(check, __file__))
