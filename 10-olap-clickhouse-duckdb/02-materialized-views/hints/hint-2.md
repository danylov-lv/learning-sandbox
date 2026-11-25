# Hint 2 -- specific

**The landing table** is the easy part: it's just a `MergeTree` with the
same 8 columns as `observations_raw`. Nothing clever there. Its only job is
to be something you can `INSERT INTO` so the view has something to react to.

**The target table's engine choice is where the two viable paths diverge:**

- `SummingMergeTree` lets you keep `count` and `price_sum` as ordinary
  `UInt64`/`Float64` columns. When ClickHouse eventually merges two parts
  that share the same `ORDER BY` key, it sums the non-key numeric columns
  for you. The view's `SELECT` just needs to produce ordinary
  `count()`/`sum(price)` values shaped to match those columns.
- `AggregatingMergeTree` asks you to declare `count`/`price_sum` as
  `AggregateFunction(count)` / `AggregateFunction(sum, Float64)` columns.
  The view then has to write into them using the `-State` combinator forms
  (`countState()`, `sumState(price)`) -- writing a plain `count()` into an
  `AggregateFunction` column is a type error.

Either is fine for this task. If you're not sure which to reach for, ask
yourself: is every column here a plain running sum, or will a future version
of this rollup need something non-additive like `avg` or `uniq`? That
question is basically the difference between the two engines.

**The `GROUP BY day, category` clause belongs inside the view's `SELECT`**,
not as an afterthought -- it's what turns "every row in this batch" into
"one partial row per key touched by this batch" before that partial gets
appended to the target.

**For `final_rollup_query()`:** the target table, read raw, can have several
rows for the same (day, category) key sitting side by side (one per batch,
until a background merge folds them together -- which may not have happened
yet). Whatever engine you picked, your `SELECT` against the target needs its
own `GROUP BY day, category`, with the right aggregation applied to each
column (`sum(...)` for `SummingMergeTree` columns, the matching `-Merge`
combinator for `AggregateFunction` columns) to guarantee one final row per
key regardless of merge timing.
