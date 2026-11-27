"""Check vacuum hygiene on the heaps that hold the module's data."""

from psycopg import sql

TABLES = ("orders", "payments", "inventory_events")
MAX_DEAD_RATIO = 0.02

RELATION_STATS = """
WITH target AS (
    SELECT to_regclass(%s) AS relation
), storage AS (
    SELECT relation FROM target
    UNION
    SELECT tree.relid
    FROM target CROSS JOIN LATERAL pg_partition_tree(target.relation) AS tree
    WHERE tree.isleaf
)
SELECT c.oid::regclass::text,
       ARRAY(
           SELECT option_name
           FROM pg_options_to_table(c.reloptions)
           WHERE CASE option_name
               WHEN 'autovacuum_enabled' THEN NOT option_value::boolean
               WHEN 'autovacuum_vacuum_scale_factor'
                   THEN option_value::real > current_setting(option_name)::real
               WHEN 'autovacuum_analyze_scale_factor'
                   THEN option_value::real > current_setting(option_name)::real
               ELSE false
           END
           ORDER BY option_name
       ),
       s.n_live_tup, s.n_dead_tup, greatest(s.last_vacuum, s.last_autovacuum),
       pg_total_relation_size(c.oid)
FROM storage
JOIN pg_class c ON c.oid = storage.relation
JOIN pg_stat_user_tables s ON s.relid = c.oid
WHERE c.relkind = 'r'
ORDER BY c.oid::regclass::text
"""


def pgstattuple_schema(cur):
    cur.execute("CREATE EXTENSION IF NOT EXISTS pgstattuple")
    cur.execute(
        """
        SELECT n.nspname
        FROM pg_extension e
        JOIN pg_namespace n ON n.oid = e.extnamespace
        WHERE e.extname = 'pgstattuple'
        """
    )
    return cur.fetchone()[0]


def check_vacuum_hygiene(cur, *, report_details=False):
    failures = []
    schema = None
    # The optional pgstattuple installation must never persist.
    with cur.connection.transaction(force_rollback=True):
        for table in TABLES:
            cur.execute(RELATION_STATS, (table,))
            relations = cur.fetchall()
            if not relations:
                reason = f"{table}: no heap table or leaf partitions found"
                failures.append(reason)
                print(f"FAIL  {reason}")
                continue

            table_failures = []
            total_live = total_dead = total_bytes = 0
            last_vacuums = []
            for relation, options, live, dead, last_vacuum, size in relations:
                label = table if relation == table else f"{table} / {relation}"
                if options:
                    table_failures.append(f"{label}: restore {', '.join(options)}")

                ratio = dead / max(live, 1)
                if ratio >= MAX_DEAD_RATIO and not options:
                    # VACUUM FULL can leave the catalog estimates stale.
                    schema = schema or pgstattuple_schema(cur)
                    cur.execute(
                        sql.SQL(
                            "SELECT tuple_count, dead_tuple_count FROM {}.pgstattuple(%s::regclass)"
                        ).format(sql.Identifier(schema)),
                        (relation,),
                    )
                    live, dead = cur.fetchone()
                    ratio = dead / max(live, 1)
                if ratio >= MAX_DEAD_RATIO:
                    table_failures.append(
                        f"{label}: dead-tuple ratio {ratio:.4f} >= {MAX_DEAD_RATIO:.2f}"
                    )

                total_live += live
                total_dead += dead
                total_bytes += size
                if last_vacuum:
                    last_vacuums.append(last_vacuum)

            if table_failures:
                failures.extend(table_failures)
                for reason in table_failures:
                    print(f"FAIL  {reason}")
            else:
                print(f"PASS  {table}: autovacuum and dead-tuple checks passed on {len(relations)} heap(s)")

            if report_details:
                last = max(last_vacuums, default="unrecorded")
                print(
                    f"info  {table}: {total_bytes / 1024**2:.1f} MiB, "
                    f"live={total_live}, dead={total_dead}, latest recorded vacuum={last}"
                )
    return failures
