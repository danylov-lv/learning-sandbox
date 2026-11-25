Concrete values and structure, still stopping short of finished test code
-- you write the actual `assert` calls and `def test_*(conn):` signatures.

**Timestamps.** Use `datetime.now(timezone.utc)` as a base `t0`, then
derive the rest with `timedelta` offsets so ordering is obvious and
reproducible: `t0`, `t0 + timedelta(minutes=1)`, `t0 + timedelta(minutes=2)`,
etc. For the "two rows sharing the exact same `scraped_at`" pagination
case, reuse the literal same `datetime` object for both rows' `scraped_at`
-- don't call `datetime.now()` twice and hope they collide, they won't.

**Idempotency test skeleton (structure, not code):**
1. One row dict, `price=Decimal("9.99")`.
2. `PriceRepo.upsert_observations(conn, [row])`.
3. Same key, `price=Decimal("7.49")`, call upsert again.
4. Read back via `PriceRepo.load_incremental(conn, since=<older than t0>)`.
5. Two assertions: `len(result) == 1`, and `result[0]["price"] ==
   Decimal("7.49")`.

**Durability test skeleton:**
1. Upsert one row through `conn`.
2. `other = psycopg.connect(postgres_dsn)` (add `postgres_dsn` as a second
   parameter to your test function, pytest will inject it same as `conn`).
3. Query through `other` (e.g. `load_incremental` needs `conn` as an
   argument -- pass `other` instead of `conn`).
4. Assert the row is there. Close `other` when done (or wrap in
   `try/finally`).

**Watermark test skeleton:**
1. `boundary = t0`. Insert `row_at_boundary` with `scraped_at=boundary`,
   `row_before` with `scraped_at=boundary - timedelta(minutes=1)`,
   `row_after` with `scraped_at=boundary + timedelta(minutes=1)`.
2. `result = PriceRepo.load_incremental(conn, since=boundary)`.
3. Assert the boundary row's `product_url` is NOT in
   `{r["product_url"] for r in result}`, and the after-row's IS, and the
   before-row's is NOT either (make sure you're not just checking one
   side).

**Pagination test skeleton:**
1. Insert N=6 rows across 3-4 distinct timestamps, with at least one pair
   sharing a timestamp (two different `product_url`s at the same
   `scraped_at`) to exercise the `id` tiebreak.
2. `limit = 2`, `after = None`, `seen_ids = []`.
3. Loop: call `page(conn, after, limit)`. If empty, stop. Extend
   `seen_ids` with the returned rows' `id`s. Set `after =
   (last_row["scraped_at"], last_row["id"])`. If `len(page result) <
   limit`, that was the last page, stop after processing it.
4. After the loop: assert `sorted(seen_ids) == sorted(all_inserted_ids)`
   AND `len(seen_ids) == len(set(seen_ids))`.
5. Guard against an infinite loop while you're developing this (e.g. cap
   iterations at N+5) in case a bug in your own test logic never triggers
   the stop condition.
