# Hint 2

`q04.sql` selects `created_at`, `status`, `total_amount`. An index built
on `(user_id, created_at)` covers the filter and the sort, but `status`
and `total_amount` aren't in it, so Postgres has to fetch each matching
row from the heap to get them. Look into the `INCLUDE` clause on
`CREATE INDEX` — columns listed there are stored in the index but aren't
part of the key, which is exactly what you want for columns you only need
to read back, not filter or sort by.
