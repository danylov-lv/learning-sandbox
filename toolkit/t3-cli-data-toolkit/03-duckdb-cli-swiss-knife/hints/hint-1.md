# Hint 1 — direction

Nothing here needs a table to be created or data to be loaded anywhere.
DuckDB can `SELECT ... FROM read_parquet('some/glob/**/*.parquet')` and
`read_csv('some/file.csv')` directly as table expressions inside a query
— treat the file paths themselves as your tables. Three separate
`duckdb -json -c "..."` invocations, one per question, is simpler than
trying to fit everything into one script variable or one query.
