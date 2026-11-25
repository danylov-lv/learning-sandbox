# Hint 1

Split this into two problems and solve them in order, don't try to design
both at once.

Problem one: what does a "good" record look like, expressed as rules a
machine can check without you eyeballing every row? That's `contracts.py`
— a static description of the contract, independent of any particular
batch of records.

Problem two: given a pile of records where some pass those rules and some
don't, how do you get the passing ones somewhere useful and the failing
ones somewhere useful too — never silently dropped, never silently
"fixed" — with enough information attached that a human could later look
at a quarantined record and understand why it's there? That's `gate.py`.

Before writing any pandera code, go fetch a chunk of live records from the
target (`GET /api/product/{id}` for a range of ids) and look at them with
your own eyes. You're not going to guess every defect shape correctly from
memory — one of them in particular is not something you'd think to check
for unless you'd actually seen a broken record.

The completeness monitor (`field_completeness` / `completeness_alert`) is
a third, smaller problem, and it's deliberately NOT the same question as
"does this record pass the contract." A field can be technically present
and syntactically fine while still being a garbage placeholder value — and
a field can go from 99% present to 60% present over time without a single
record ever failing a strict validity check. Both are worth watching, for
different reasons.
