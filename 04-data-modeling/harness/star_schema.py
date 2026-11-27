import re

import psycopg
from psycopg import sql

from common import SPAN_DAYS

FACT = "fact_price_observation"
HISTORY_DIMENSIONS = {"dim_shop", "dim_product"}
REQUIRED_TABLES = HISTORY_DIMENSIONS | {"dim_date", FACT}
REPORT_TABLES = {
    "q09": {FACT, "dim_product", "dim_date"},
    "q10": {FACT, "dim_shop"},
    "q11": {FACT, "dim_product", "dim_date"},
}
STATEMENT_TIMEOUT_MS = 120_000


def check_structure(conn_kwargs, expected_fact_count):
    try:
        with psycopg.connect(**conn_kwargs) as conn:
            conn.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
            return check_tables(conn, expected_fact_count)
    except psycopg.Error as exc:
        return f"star-schema check failed: {str(exc).splitlines()[0]}"


def check_tables(conn, expected_fact_count):
    relations = dict(conn.execute(
        """SELECT c.relname, c.relkind
           FROM pg_catalog.pg_class AS c
           JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
           WHERE n.nspname = 'mart' AND c.relname = ANY(%s)""",
        (sorted(REQUIRED_TABLES),),
    ).fetchall())
    for table in sorted(REQUIRED_TABLES):
        if relations.get(table) not in {"r", "p"}:
            return f"mart.{table} must be a physical table"

    for table in sorted(HISTORY_DIMENSIONS):
        columns = conn.execute(
            """SELECT attname FROM pg_catalog.pg_attribute
               WHERE attrelid = %s::regclass AND attnum > 0 AND NOT attisdropped""",
            (f"mart.{table}",),
        ).fetchall()
        missing = {"valid_from", "valid_to"} - {name for name, in columns}
        if missing:
            return f"mart.{table} is missing column(s): {', '.join(sorted(missing))}"
        populated, invalid = conn.execute(sql.SQL(
            """SELECT EXISTS (SELECT FROM {table}),
                      EXISTS (SELECT FROM {table}
                              WHERE valid_from IS NULL OR valid_to <= valid_from)"""
        ).format(table=sql.Identifier("mart", table))).fetchone()
        if not populated:
            return f"mart.{table} has zero rows"
        if invalid:
            return f"mart.{table} has an invalid validity interval"

    date_count, = conn.execute("SELECT count(*) FROM mart.dim_date").fetchone()
    if date_count < SPAN_DAYS:
        return f"mart.dim_date needs one row per date in the {SPAN_DAYS}-day business period"

    fact_count, = conn.execute("SELECT count(*) FROM mart.fact_price_observation").fetchone()
    if fact_count != expected_fact_count:
        return f"mart.{FACT} has {fact_count} rows; expected {expected_fact_count} deduplicated observations"
    return None


def report_relations(cur):
    cur.execute("""
        WITH RECURSIVE relations(oid) AS (
            SELECT 'pg_temp.pricewatch_report'::regclass::oid
            UNION
            SELECT d.refobjid
            FROM relations AS r
            JOIN pg_catalog.pg_rewrite AS w ON w.ev_class = r.oid
            JOIN pg_catalog.pg_depend AS d
              ON d.classid = 'pg_catalog.pg_rewrite'::regclass AND d.objid = w.oid
            WHERE w.rulename = '_RETURN'
              AND d.refclassid = 'pg_catalog.pg_class'::regclass
              AND d.refobjid <> r.oid
        )
        SELECT n.nspname, c.relname
        FROM relations AS r
        JOIN pg_catalog.pg_class AS c ON c.oid = r.oid
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
        WHERE r.oid <> 'pg_temp.pricewatch_report'::regclass::oid
    """)
    return cur.fetchall()


def uses_validity_predicate(plan):
    nodes = [plan]
    for node in nodes:
        nodes.extend(node.get("Plans", []))
    history_aliases = {
        node["Alias"] for node in nodes
        if node.get("Schema") == "mart" and node.get("Relation Name") in HISTORY_DIMENSIONS
    }
    if not history_aliases:
        return False
    aliases = "|".join(re.escape(alias.replace('"', '""')) for alias in sorted(history_aliases))
    validity_reference = re.compile(
        rf'(?<![\w$])(?:"(?:{aliases})"|(?:{aliases}))\.(?:"(?:valid_from|valid_to)"|(?:valid_from|valid_to)\b)'
    )
    conditions = (
        "Filter", "One-Time Filter", "Join Filter", "Hash Cond",
        "Merge Cond", "Index Cond", "Recheck Cond",
    )
    for node in nodes:
        for condition in conditions:
            expression = re.sub(r"'(?:[^']|'')*'", "", node.get(condition, ""))
            if validity_reference.search(expression):
                return True
    return False


def prepare_report(cur, qkey, text):
    cur.execute("SET LOCAL search_path = mart")
    # Record resolved relation dependencies before the planner can remove joins.
    cur.execute(sql.SQL("CREATE TEMP VIEW pricewatch_report AS {}").format(sql.SQL(text)), prepare=True)
    relations = report_relations(cur)
    outside = sorted(f"{schema}.{name}" for schema, name in relations if schema != "mart")
    if outside:
        return f"query uses relations outside mart: {', '.join(outside)}"
    missing = REPORT_TABLES[qkey] - {name for _, name in relations}
    if missing:
        return f"query must use mart relations: {', '.join(sorted(missing))}"

    cur.execute("EXPLAIN (VERBOSE, FORMAT JSON) SELECT * FROM pg_temp.pricewatch_report")
    if uses_validity_predicate(cur.fetchone()[0][0]["Plan"]):
        return "query must use the dimension versions selected when loading the fact"
    return None
