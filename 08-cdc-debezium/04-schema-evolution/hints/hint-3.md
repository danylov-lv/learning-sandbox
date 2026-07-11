Concretely, `apply_change` needs three pieces:

1. `ensure_replica_table` (already given) creates `replica.offers` with
   `discount_pct NUMERIC(5,2)` nullable, before the source even has the
   column. That's what makes the replica schema "ahead of" the source --
   it never needs an `ALTER` of its own during this task.
2. For `op in ('r', 'c', 'u')`: pull every field off `after` with `.get`,
   e.g. `after.get("discount_pct")` (defaults to `None` if absent -- don't
   pass a second argument, `None` is exactly the value you want for a
   missing column), and upsert one row into `replica.offers` keyed on
   `offer_id`, using `ON CONFLICT (offer_id) DO UPDATE SET ...` for every
   non-key column. This single code path has to work unchanged whether or
   not `after` happens to contain `discount_pct` this time.
3. For `op == 'd'`: `DELETE FROM replica.offers WHERE offer_id = %s` using
   `before["offer_id"]` (safe to index -- `offer_id` is the primary key
   and is always present in a delete's `before` image, additive columns
   don't change that).

Commit once per event, right there in `apply_change` (or right after it
returns, before the caller commits the Kafka offset -- either is fine as
long as the Postgres write lands before the offset commit).

Worth thinking through, even though you don't need to write code for it:
why would a `DROP COLUMN` or a type change (e.g. `NUMERIC` ->
`TEXT`) be much harder to handle than this `ADD COLUMN`? What would break
in a consumer that only knows the defensive-read trick this task teaches?
(Hint: `.get()` protects you from a MISSING key. It does nothing for a key
that's still present but now means something different, or is gone for
rows the consumer still thinks exist.)
