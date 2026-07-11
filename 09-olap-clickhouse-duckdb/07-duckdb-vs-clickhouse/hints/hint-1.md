You've already written this exact aggregate at least once in this module
(task 01's `category_instock_agg()`, or task 05's `ch_answer()`/`pg_answer()`
if you've done that one, or task 06's `per_category_instock()`). This task
doesn't ask you to invent a new query -- it asks you to run the SAME query
against two different engines and pay attention to what changes and what
doesn't. Before writing any code, be clear in your own head about what MUST
match between `ch_answer()` and `duck_answer()` (the shape of the result, the
filter, the grouping, the numbers) and what's allowed to differ (the SQL
dialect, how you open the connection, how long it takes).
