# Hint 3

For "When to just use Postgres," resist the urge to write a universal
rule. Instead, name the conditions that would make you say no to your
teammate for a SPECIFIC workload: a catalog small enough that a `jsonb`
column with GIN answers every query fast enough, a coordination need that's
actually just "one worker at a time" (an advisory lock, not a distributed
fencing token), a queue with low enough throughput that `SELECT ... FOR
UPDATE SKIP LOCKED` is plenty. If your answer to "when Postgres" is just
"when the data is small," you haven't used what tasks 01-06 taught you
about coordination primitives and index shape — go back and be more
specific.

For "Operational and consistency costs," think about what breaks silently.
A Redis restart with no persistence configured loses your rate-limiter
counters and your dedup Bloom filter — is that a correctness problem or
just a cold-start blip? A dead consumer in a Streams group leaves entries
pending until something calls `XAUTOCLAIM` — who's responsible for that in
production? A Mongo write with the default write concern acknowledges
before it's durable on disk — where would that matter for the documents you
built in task 05? Contrast each of those against what Postgres gives you by
default (WAL, ACID transactions) and be concrete about the gap, not just
"NoSQL is less consistent."

For the checklist, keep it short — five to eight bullets you could actually
scan under time pressure in a real design review, not a compressed
restatement of every section above.
