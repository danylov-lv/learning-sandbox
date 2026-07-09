Start from what actually crosses the JVM/Python boundary in each variant, not from "UDFs are slow" as a slogan.

A plain `F.udf` makes Spark's JVM side serialize each row's arguments (pickle them), hand them to a long-lived Python worker process one row at a time, wait for your Python function to run, and pickle the result back. That per-row round trip — not "Python is slow" in the abstract — is the tax. It shows up in the physical plan as a `BatchEvalPython` node (the name is a little misleading: it batches the *transport*, but your Python function still runs once per row inside that batch).

A `pandas_udf` changes what gets handed across the boundary: instead of one row's values, Python receives a whole Arrow-backed pandas Series covering many rows at once, and your function operates on the whole Series with vectorized pandas/numpy calls — no Python-level loop over rows. The boundary crossing still happens (Arrow doesn't make the JVM/Python split disappear), but it happens once per batch instead of once per row, and the work inside Python is vectorized instead of interpreted row-by-row. This shows up as an `ArrowEvalPython` node.

Built-ins skip Python entirely. `when`/`otherwise`, casts, and struct field access compile down to Catalyst expressions that run inside the JVM, in the same execution as everything else in the query — no serialization, no process boundary, and (unlike either UDF variant) fully visible to the optimizer.

Before writing code, go find each of these three node names by building tiny throwaway DataFrames of your own and calling `.explain()` on them. Confirm you can find `BatchEvalPython`, `ArrowEvalPython`, and their absence with your own eyes before you build the real functions.
