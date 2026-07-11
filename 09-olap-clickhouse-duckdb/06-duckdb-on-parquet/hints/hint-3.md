Concrete shape for each function, without handing you the exact SQL:

- `total_rows(con)`: one query, `SELECT count(*) FROM read_parquet(<glob>,
  hive_partitioning=true)`, run through `con.execute(...)`, and pull the
  single scalar back out (`.fetchone()` gives you a one-element tuple).
  Cast it to a plain `int` before returning.

- `per_category_instock(con)`: `SELECT category, count(*), avg(price) FROM
  read_parquet(<glob>, hive_partitioning=true) WHERE in_stock GROUP BY
  category`, then `.fetchall()` and build a dict keyed by the first column,
  valued `(second, third)`, from the returned rows. Don't forget to cast the
  count to `int` and the average to `float` if you want to be safe about
  types the validator compares against JSON-loaded numbers.

- `one_category_files(con, category)`: `SELECT DISTINCT filename FROM
  read_parquet(<glob>, hive_partitioning=true, filename=true) WHERE category
  = ?`, parameterized (DuckDB's Python API accepts a second argument to
  `execute` -- a list of parameter values -- with `?` placeholders in the
  SQL), or built with an f-string if you'd rather. `.fetchall()` gives you a
  list of one-tuples; flatten it into a plain list (or set) of path strings
  before returning. For the seeded 8-category lake, filtering to one
  category should give you back a list of length exactly 1.

Once all three return something, sanity-check `one_category_files` by eye
first: print what you get back for `"electronics"` and for a couple of other
categories, and confirm each is a single path whose directory component
literally reads `category=<that category>`. If you ever see more than one
path in the list, or a path that doesn't match the category you asked for,
the WHERE clause isn't landing on the partition column the way you think it
is -- double check you're filtering on `category` (the value DuckDB derived
from the Hive path) and not on some other column, and that
`hive_partitioning=true` is actually present in the `read_parquet(...)` call
you're running (it's easy to add `filename=true` and forget the other
option, or vice versa).
