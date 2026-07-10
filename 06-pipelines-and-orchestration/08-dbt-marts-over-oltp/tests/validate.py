"""Validator for 08-dbt-marts-over-oltp.

Run from this task's directory:
    uv run python tests/validate.py

Targets module 02's live Postgres (the Kupitron marketplace OLTP), not
module 06's warehouse. Requires module 02's docker-compose stack up and
seeded — see README "What's given" if this fails at the preflight step.
"""

import os
import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import guarded, not_passed, passed  # noqa: E402

SRC_DIR = TASK_ROOT / "src"

PG02_HOST = os.environ.get("SANDBOX_02_HOST", "localhost")
PG02_PORT = int(os.environ.get("SANDBOX_02_PORT", "54302"))
PG02_DB = os.environ.get("SANDBOX_02_DB", "sandbox")
PG02_USER = os.environ.get("SANDBOX_02_USER", "sandbox")
PG02_PASSWORD = os.environ.get("SANDBOX_02_PASSWORD", "sandbox")

STAGING_SCHEMA = "dbt_analytics"
MARTS_SCHEMA = "dbt_analytics_marts"
EXPECTED_STAGING_VIEWS = {"stg_orders", "stg_order_items", "stg_products", "stg_categories"}
AGG_MART = "mart_daily_category_gmv"
INCR_MART = "fct_order_line_items"

# GMV definition the validator recomputes independently — must match the
# rule stated in README "What's required": completed orders only, i.e.
# excluding 'pending' (never paid) and 'cancelled'.
GMV_ORDER_FILTER = "status NOT IN ('pending', 'cancelled')"


def pg02_connect():
    import psycopg

    conninfo = (
        f"host={PG02_HOST} port={PG02_PORT} dbname={PG02_DB} "
        f"user={PG02_USER} password={PG02_PASSWORD}"
    )
    try:
        return psycopg.connect(conninfo)
    except psycopg.Error as e:
        not_passed(
            f"could not connect to module 02 Postgres on port {PG02_PORT}: {e} — "
            "is `02-sql-optimization` docker compose up and seeded?"
        )


def public_schema_relations(conn):
    with conn.cursor() as cur:
        cur.execute(
            "select relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'public' and c.relkind in ('r', 'v', 'm')"
        )
        return {row[0] for row in cur.fetchall()}


def schema_relations(conn, schema, relkinds=("r", "v")):
    with conn.cursor() as cur:
        cur.execute(
            "select relname, relkind from pg_class c join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = %s and c.relkind = ANY(%s)",
            (schema, list(relkinds)),
        )
        return dict(cur.fetchall())


def run_dbt_build():
    result = subprocess.run(
        ["uv", "run", "dbt", "build", "--project-dir", str(SRC_DIR), "--profiles-dir", str(SRC_DIR)],
        cwd=str(TASK_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    return result


@guarded
def main():
    conn = pg02_connect()

    with conn.cursor() as cur:
        cur.execute("select count(*) from products")
        if cur.fetchone()[0] == 0:
            not_passed("module 02 `products` table is empty — run its seed generator first")

    before_public = public_schema_relations(conn)

    result = run_dbt_build()
    if result.returncode != 0:
        tail = "\n".join(result.stdout.splitlines()[-40:])
        not_passed(f"`dbt build` exited {result.returncode}:\n{tail}")

    after_public = public_schema_relations(conn)
    new_in_public = after_public - before_public
    if new_in_public:
        not_passed(
            f"dbt build created object(s) in module 02's `public` schema: {sorted(new_in_public)} — "
            "check +schema config and generate_schema_name.sql"
        )

    staging_relations = schema_relations(conn, STAGING_SCHEMA, relkinds=("v",))
    missing_staging = EXPECTED_STAGING_VIEWS - set(staging_relations)
    if missing_staging:
        not_passed(f"schema `{STAGING_SCHEMA}` is missing expected view(s): {sorted(missing_staging)}")

    marts_relations = schema_relations(conn, MARTS_SCHEMA, relkinds=("r",))
    for mart in (AGG_MART, INCR_MART):
        if mart not in marts_relations:
            not_passed(f"schema `{MARTS_SCHEMA}` is missing expected table `{mart}`")

    with conn.cursor() as cur:
        cur.execute(f"select count(*) from {MARTS_SCHEMA}.{AGG_MART}")
        if cur.fetchone()[0] == 0:
            not_passed(f"{MARTS_SCHEMA}.{AGG_MART} is empty")

        cur.execute(f"select count(*) from {MARTS_SCHEMA}.{INCR_MART}")
        rc1 = cur.fetchone()[0]
        if rc1 == 0:
            not_passed(f"{MARTS_SCHEMA}.{INCR_MART} is empty")

        # Reference aggregate 1: total GMV across all rows must match an
        # independent recomputation straight off the source tables.
        cur.execute(f"select sum(gmv) from {MARTS_SCHEMA}.{AGG_MART}")
        mart_total_gmv = cur.fetchone()[0]

        cur.execute(
            f"""
            select sum(oi.quantity * oi.unit_price)
            from order_items oi
            join orders o on o.id = oi.order_id
            where o.{GMV_ORDER_FILTER}
            """
        )
        expected_total_gmv = cur.fetchone()[0]

        if mart_total_gmv is None or expected_total_gmv is None:
            not_passed("could not compute total GMV for cross-check (NULL result)")
        if abs(float(mart_total_gmv) - float(expected_total_gmv)) > 0.01:
            not_passed(
                f"{AGG_MART} total gmv={mart_total_gmv}, independently recomputed "
                f"total={expected_total_gmv} — mismatch"
            )

        # Reference aggregate 2: pick one (date, category_family) pair from
        # the mart itself and cross-check its row against a direct query.
        cur.execute(
            f"select order_date, category_family, gmv, order_count "
            f"from {MARTS_SCHEMA}.{AGG_MART} order by order_date, category_family limit 1"
        )
        sample = cur.fetchone()
        if sample is None:
            not_passed(f"{AGG_MART} returned no rows to sample for the per-row cross-check")
        sample_date, sample_family, sample_gmv, sample_order_count = sample

        cur.execute(
            f"""
            select coalesce(sum(oi.quantity * oi.unit_price), 0), count(distinct o.id)
            from order_items oi
            join orders o on o.id = oi.order_id
            join products p on p.id = oi.product_id
            join categories c on c.id = p.category_id
            where o.{GMV_ORDER_FILTER}
              and o.created_at::date = %s
              and c.family = %s
            """,
            (sample_date, sample_family),
        )
        expected_gmv, expected_order_count = cur.fetchone()

        if abs(float(sample_gmv) - float(expected_gmv)) > 0.01:
            not_passed(
                f"{AGG_MART} row (date={sample_date}, family={sample_family}) gmv={sample_gmv}, "
                f"independently recomputed gmv={expected_gmv} — mismatch"
            )
        if int(sample_order_count) != int(expected_order_count):
            not_passed(
                f"{AGG_MART} row (date={sample_date}, family={sample_family}) order_count={sample_order_count}, "
                f"independently recomputed order_count={expected_order_count} — mismatch"
            )

    conn.close()

    # Second build: proves the incremental model is stable, not append-only.
    result2 = run_dbt_build()
    if result2.returncode != 0:
        tail = "\n".join(result2.stdout.splitlines()[-40:])
        not_passed(f"second `dbt build` exited {result2.returncode}:\n{tail}")

    conn = pg02_connect()
    with conn.cursor() as cur:
        cur.execute(f"select count(*) from {MARTS_SCHEMA}.{INCR_MART}")
        rc2 = cur.fetchone()[0]
    conn.close()

    if rc2 != rc1:
        not_passed(
            f"{INCR_MART} row count changed between two consecutive `dbt build` runs "
            f"({rc1} -> {rc2}) — an incremental model over a static source should be stable"
        )

    passed("staging views, both marts, dbt tests, and incremental stability all check out")


if __name__ == "__main__":
    main()
