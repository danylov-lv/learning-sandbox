"""Stub for the pipeline-monitor Deployment's process.

Your code, and it should stay small. Two acceptable shapes:

  1. An alert-sink-style stdlib HTTP server (http.server /
     BaseHTTPRequestHandler — see the module's alert-sink for the idea)
     exposing something like GET /health that queries ops.load_audit and
     reports whether the most recent successful load is fresher than a
     threshold.

  2. A plain forever-loop: every N seconds, check max(finished_at) for
     successful ops.load_audit rows, log OK/STALE, exit nonzero only on
     unrecoverable errors (a stale pipeline is a *reported* condition,
     not a crash — the Deployment restarting you won't make the data
     fresher).

Either way the warehouse DSN and the freshness threshold come from env
vars supplied by the chart. This is the process you will measure with
`kubectl top` / `docker stats` to derive the Deployment's resource
requests and limits.
"""

from __future__ import annotations


def main() -> int:
    # TODO: implement one of the two shapes above.
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
