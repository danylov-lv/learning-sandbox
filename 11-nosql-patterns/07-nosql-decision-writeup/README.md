# 07 — When NoSQL beats relational, and when it doesn't (writeup)

## Backstory

A teammate has been reading about how "Postgres doesn't scale" and shows up
with a plan: "Let's move everything to MongoDB and Redis — no more schema
migrations, no more slow queries, everything's fast and flexible." You've
just spent six tasks actually building the things NoSQL stores are supposed
to be good at: an atomic Redis rate limiter, a distributed lock with a
fencing token, exact-set vs Bloom-filter dedup, a Redis Streams consumer
group with acknowledgement and reclaim, a MongoDB document model with real
compound and multikey indexes, and the same semi-structured workload run
side by side against Postgres JSONB with GIN. You have opinions now that are
backed by things you built and measured, not opinions borrowed from a blog
post.

Write the memo that answers your teammate honestly. Not "NoSQL bad" and not
"NoSQL good" — a reasoned, per-workload position: which of the six patterns
you just built earn a dedicated store, which of them are actually just a
data-structure server doing coordination work Postgres was never trying to
do, and which of the "documents" you modeled in Mongo would have been just
as happy, or happier, as a JSONB column with a GIN index. The teammate is
about to make an infrastructure decision. Give them the version grounded in
evidence, not the version grounded in a tech blog.

## What's given

- This module's task suite (01-06), which has taught you:
  - `01` — an atomic Redis rate limiter: what "atomic check-and-record" buys
    you that a naive check-then-act read/write against any database (SQL or
    not) cannot.
  - `02` — a distributed lock: `SET NX PX`, a fencing token, and a safe
    compare-and-delete release — mutual exclusion across processes as a
    coordination primitive, not a data-storage problem.
  - `03` — exact-set vs Bloom-filter dedup: the memory/accuracy tradeoff of
    probabilistic set membership (RedisBloom `BF.*`) against an exact `SET`,
    for a seen-url filter that doesn't need to be perfect, only cheap.
  - `04` — a Redis Streams consumer group: durable hand-off, `XACK`, and
    reclaiming a dead consumer's pending entries via `XAUTOCLAIM`/`XPENDING`
    — a queue, not a table.
  - `05` — MongoDB document modeling: embedding a heterogeneous, genuinely
    variable-shaped product catalog, compound and multikey indexes, and an
    aggregation pipeline, with `explain('queryPlanner')` proof the indexes
    are actually used.
  - `06` — MongoDB vs Postgres JSONB: the *same* semi-structured workload
    modeled and indexed both ways — Mongo's indexes against Postgres GIN
    containment queries — so you have a real head-to-head rather than a
    reputation.
- A structured template (`ANSWER.md`) with five required section headings
  and guiding prompts under each — no answers filled in.
- `NOTES.md` for your post-task reflection.

## What's required

Fill in every section of `ANSWER.md` with real substance, grounded in what
you built and measured in tasks 01-06:

1. `## Redis beyond cache — what each primitive buys you` — for the rate
   limiter, the distributed lock, Bloom dedup, and the streams consumer
   group: name the actual coordination problem each one solves (an atomic
   check-and-record, mutual exclusion across processes, probabilistic
   membership at a memory budget a real set can't match, durable
   at-least-once hand-off with acknowledgement) and say plainly why a
   relational database is the wrong tool for that specific problem — not
   because it's "slow," but because it isn't built to make those operations
   atomic or cheap in the first place.

2. `## MongoDB vs Postgres JSONB` — where the document store genuinely
   earned its place in task 05/06 (schema-per-document flexibility, native
   array/multikey indexing, an aggregation pipeline that reads naturally),
   and where Postgres JSONB with a GIN index already gave you the same
   answer with one engine instead of two. Be specific about the containment
   query and the index shape, not just "Mongo is more flexible."

3. `## When to just use Postgres` — Postgres is the default. State what has
   to be true about a workload — data volume, query pattern, consistency
   need, team operational capacity — before you'd add Redis or Mongo next to
   it, and what it would take for you to say "no, this one stays in
   Postgres" to the exact teammate who's pushing to move everything.

4. `## Operational and consistency costs` — every store in this module
   added to what you have to run, patch, back up, and reason about failure
   modes for. What does Redis actually guarantee about durability across a
   restart? What does MongoDB give you by default versus with a write
   concern? What does "eventually consistent" or "read-your-own-writes"
   concretely mean for a dedup filter, a rate limiter, or a materialized
   document — where would a consistency gap actually bite in a
   scrape-ingestion pipeline?

5. `## Decision checklist` — a short, bulleted heuristic you would actually
   paste into a design doc the next time someone proposes a new datastore.
   Not a restatement of the sections above — the compressed version you'd
   want in front of you in the meeting.

Also fill in `NOTES.md`: what you learned, gotchas you hit, open questions a
real polyglot-persistence decision would still need answered.

## Completion criteria

From this task's directory:

```bash
uv run python tests/validate.py
```

The validator checks:
- `ANSWER.md` exists and contains all five required `## ` section headings
  (exact match).
- Each section is substantially filled with your own prose (at least ~200
  characters of real content) and no longer contains its `[fill in`
  placeholder marker.
- Somewhere in the document, at least 6 of the following 8 grounding
  concepts are referenced: Bloom, rate limit (or rate-limit), distributed
  lock, consumer group, GIN, containment, JSONB, idempoten(t/cy) — proof the
  positions are tied to what tasks 01-06 actually built, not asserted from
  first principles.
- `NOTES.md` is filled beyond the template headers (at least ~150
  characters).
- On success: `PASSED` with a per-section character count. On failure:
  `NOT PASSED: <which section is empty, still a stub, or under-grounded>`,
  exit 1, no traceback.

## Estimated evenings

1

## Topics to read up on

- Redis as a coordination/primitive layer (atomic ops, locks, probabilistic
  structures, streams) vs Redis as a general-purpose datastore
- Bloom filter tradeoffs: false-positive rate vs memory, and why "probably
  seen" is good enough for a dedup filter but would be wrong for billing
- Document model vs relational+JSONB: when schema flexibility is a genuine
  win and when it's just deferred validation
- Postgres GIN indexes and the `@>` containment operator over `jsonb`
- Polyglot persistence: the real cost of a second (or third) store — more
  moving parts, more failure modes, more things to keep in sync — versus the
  cost of forcing a bad fit into your one existing store
- CAP-theorem-flavored consistency tradeoffs for Redis, MongoDB, and
  Postgres specifically (not the theorem in the abstract): what each one
  actually promises about durability and read freshness by default

## `.authoring/` is off-limits

`.authoring/` (at the module root) holds spoilers for this module — the
full data contract, RNG draw order, ground-truth internals, and design
rationale for every task. Don't read it before finishing this task.
