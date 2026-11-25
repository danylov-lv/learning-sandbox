# Hint 2

A practical drift signal: run your existing lazy validation, look at
`failure_cases` grouped by `column` and `check`. If a huge share of the
batch (pick a threshold — something like "the overwhelming majority of rows"
rather than task 05's expected sub-2% invalid rate) fails on the *same*
column/check combination, that's a structural problem with the batch, not a
handful of bad records. Branch your DAG logic on that distinction: row-level
failures go to quarantine as before; a batch-level failure pattern triggers
the alert path and stops that day short of a partial `core` load.

For the alert, `POST` a small JSON body to `http://alert-sink:8000/alert` —
same call shape as `smoke_env.py`'s `check_alert_sink` task, just with a
body that has `type`, `dt`, and a description field instead of
`{"source": ..., "level": ...}`.

For the price-string normalizer: figure out which of the two given locale
styles a value is in *without* trying to guess from the separators alone.
One of the two formats always carries something at one end of the string
that plainly marks which convention it is — find that marker and branch on
it before you touch the numeric parsing. Only after you know which style
you're looking at should you worry about stripping symbols and swapping
separators.
