"""Single source of truth for what modules exist and how CI should treat each one.

Stdlib only -- imported by detect_changes.py, checks.py, run_module_ci.py,
repo_guards.py and tests/validate.py, all of which must run with a bare
GitHub-runner python (no third-party packages installed).

To add a future module: add one row to MODULES. Nothing else in ci-meta
needs to change.
"""

from __future__ import annotations

from typing import NamedTuple


class Module(NamedTuple):
    path: str  # repo-relative directory
    kind: str  # "python" | "rust" | "pnpm"
    services: str  # "none" | "light" | "heavy"
    note: str  # short human-readable rationale, mainly for heavy/skip modules


# Order matters only for readability and for deterministic matrix ordering
# in detect_changes.py output -- it mirrors the repo's own module numbering.
MODULES: dict[str, Module] = {
    "01-sql-foundations": Module(
        "01-sql-foundations", "python", "light",
        "Postgres only; boots and reaches healthy on a hosted runner",
    ),
    "02-sql-optimization": Module(
        "02-sql-optimization", "python", "heavy",
        "Postgres tuned for a multi-GB bloat/locking/partitioning scenario; "
        "booting the empty container proves nothing about the seeded "
        "workload, so it is not run live on a hosted runner",
    ),
    "03-data-modeling": Module(
        "03-data-modeling", "python", "light",
        "Postgres only; boots and reaches healthy on a hosted runner",
    ),
    "04-storage-and-formats": Module(
        "04-storage-and-formats", "python", "heavy",
        "MinIO plus multi-GB Parquet/Delta datasets; not feasible on a hosted runner",
    ),
    "05-distributed-processing-spark": Module(
        "05-distributed-processing-spark", "python", "heavy",
        "PySpark cluster plus MinIO; not feasible on a hosted runner",
    ),
    "06-pipelines-and-orchestration": Module(
        "06-pipelines-and-orchestration", "python", "heavy",
        "Airflow plus Postgres plus MinIO multi-container stack; not feasible on a hosted runner",
    ),
    "07-streaming": Module(
        "07-streaming", "python", "heavy",
        "Postgres plus redpanda (Kafka API); not feasible on a hosted runner",
    ),
    "08-cdc-debezium": Module(
        "08-cdc-debezium", "python", "heavy",
        "Two Postgres instances plus redpanda plus Kafka Connect/Debezium; "
        "not feasible on a hosted runner",
    ),
    "09-olap-clickhouse-duckdb": Module(
        "09-olap-clickhouse-duckdb", "python", "heavy",
        "ClickHouse at 50M-row scale; not feasible on a hosted runner",
    ),
    "10-nosql-patterns": Module(
        "10-nosql-patterns", "python", "light",
        "Redis Stack, MongoDB, Postgres; all boot and reach healthy on a hosted runner",
    ),
    "11-python-concurrency": Module(
        "11-python-concurrency", "python", "none",
        "No services; static checks only",
    ),
    "12-api-engineering": Module(
        "12-api-engineering", "python", "light",
        "Postgres and Redis; boot and reach healthy on a hosted runner",
    ),
    "13-scraping-at-scale": Module(
        "13-scraping-at-scale", "python", "heavy",
        "Local target site plus Prometheus plus Grafana multi-container stack; "
        "not feasible on a hosted runner",
    ),
    "14-stats-and-ml-foundations": Module(
        "14-stats-and-ml-foundations", "python", "none",
        "No services; static checks only",
    ),
    "15-llm-in-pipelines": Module(
        "15-llm-in-pipelines", "python", "heavy",
        "Ollama needs a GPU-capable host; not feasible on a hosted runner",
    ),
    "16-testing-engineering": Module(
        "16-testing-engineering", "python", "none",
        "Uses testcontainers directly inside its own test suite, not a module-level docker-compose.yml",
    ),
    "17-system-design": Module(
        "17-system-design", "python", "none",
        "Writing module; no services, pure document/capacity-model checks",
    ),
    "18-rust-track": Module(
        "18-rust-track", "rust", "none",
        "Cargo workspace; no services",
    ),
    "19-ts-track": Module(
        "19-ts-track", "pnpm", "none",
        "pnpm workspace; no services",
    ),
    "20-kubernetes": Module(
        "20-kubernetes", "python", "none",
        "Runs a kind cluster, not docker-compose; special-cased, not booted in CI",
    ),
    "toolkit/t1-ai-assisted-engineering": Module(
        "toolkit/t1-ai-assisted-engineering", "python", "none",
        "No services; static checks only",
    ),
    "toolkit/t2-modern-python-toolchain": Module(
        "toolkit/t2-modern-python-toolchain", "python", "none",
        "No services; static checks only",
    ),
    "toolkit/t3-cli-data-toolkit": Module(
        "toolkit/t3-cli-data-toolkit", "python", "none",
        "No services; static checks only",
    ),
    "toolkit/t4-git-advanced": Module(
        "toolkit/t4-git-advanced", "python", "none",
        "No services; static checks only",
    ),
}

_STUB_MARKERS: dict[str, tuple[str, ...]] = {
    "python": ("NotImplementedError",),
    "rust": ("todo!", "unimplemented!"),
    "pnpm": ("not implemented",),
}


def stub_marker(kind: str) -> tuple[str, ...]:
    """Marker string(s) that indicate an unsolved learner stub for this module kind."""
    try:
        return _STUB_MARKERS[kind]
    except KeyError as exc:
        raise ValueError(f"unknown module kind: {kind!r}") from exc


def all_module_ids() -> list[str]:
    return list(MODULES.keys())


def get(module_id: str) -> Module:
    try:
        return MODULES[module_id]
    except KeyError as exc:
        raise KeyError(f"no such module in registry: {module_id!r}") from exc
