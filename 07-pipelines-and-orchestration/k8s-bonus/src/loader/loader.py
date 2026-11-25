"""Stub entrypoint for the containerized daily loader.

Repackage your t02/t09 incremental-loader logic here: one invocation loads
exactly one day (staging -> contract -> core, or however far your loader
went in those tasks) against the module's warehouse, then exits 0 on
success / nonzero on failure so the CronJob's Job semantics work.

Decide how the target day arrives (CLI arg vs. env var) and how the
warehouse DSN arrives (env var set by the chart — never hardcode the
in-cluster hostname here; the same image should run against compose and
against kind).
"""

from __future__ import annotations


def main() -> int:
    # TODO: parse target day + warehouse DSN from the environment/argv,
    # run your incremental load for that day, return an exit code.
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
