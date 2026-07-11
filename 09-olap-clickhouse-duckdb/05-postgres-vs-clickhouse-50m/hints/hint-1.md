Both functions must return a plain Python dict built entirely from what the
database already computed -- do the counting and averaging as a `GROUP BY`
in SQL, on both sides. If you find yourself looping over fetched rows to
add up counts or prices in Python, stop: that's exactly what this task is
measuring the database engine's own performance on, and doing it in Python
defeats the comparison (and will be painfully slow at real scale besides).

Both queries answer the identical question against a different table:
"for each category, over rows that are in stock, how many rows and what's
the average price". Write it once in your head in plain English before
touching either engine's SQL dialect.
