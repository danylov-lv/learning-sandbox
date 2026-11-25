"""Pass/fail plumbing shared by every task validator in this module.

Convention (matches the rest of the repo): a validator prints exactly one
line and exits. On success: `PASSED` (optionally with a trailing detail
line). On failure: `NOT PASSED: <reason>` and exit 1. No raw tracebacks.
"""

from __future__ import annotations

import functools
import sys
import traceback
from typing import Callable, NoReturn, TypeVar

F = TypeVar("F", bound=Callable[..., None])


def not_passed(reason: str) -> NoReturn:
    print(f"NOT PASSED: {reason}")
    sys.exit(1)


def passed(msg: str = "") -> None:
    print("PASSED")
    if msg:
        print(msg)


def _last_line(exc: BaseException) -> str:
    """Return the last non-empty line of an exception's formatted traceback.

    This is the line closest to "what went wrong" (the exception's own
    repr) without leaking the full call stack to the learner.
    """
    lines = traceback.format_exception_only(type(exc), exc)
    for line in reversed(lines):
        line = line.strip()
        if line:
            return line
    return repr(exc)


def guarded(fn: F) -> Callable[..., None]:
    """Wrap a validator's main() so any uncaught exception becomes a single
    NOT PASSED line instead of a raw traceback.

    Usage:
        @guarded
        def main() -> None:
            ...
            passed()

        if __name__ == "__main__":
            main()
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs) -> None:
        try:
            fn(*args, **kwargs)
        except SystemExit:
            raise
        except BaseException as exc:  # noqa: BLE001 - intentional catch-all
            not_passed(_last_line(exc))

    return wrapper
