"Idempotent" is a claim about the relationship between inputs and outputs,
not about how careful your code looks. The only way to actually know a load
is idempotent is to run it twice against the same input and compare state
before and after the second run — which is exactly what the validator does
to you. Before writing code, decide: what does "the same" mean for one row
in `staging.price_records_raw`? If you rerun today against the same static
file, will a given `(dt, line_no)` always map to the same `payload`, or
could it legitimately differ? Your answer determines whether "insert and
ignore conflicts" is safe or whether you need to overwrite on conflict.

Also think about failure. A task that half-finishes and then throws is not
idempotent by accident — you have to design for it. If your load writes
rows one at a time and dies halfway through a day's file, what does the
next run see?
