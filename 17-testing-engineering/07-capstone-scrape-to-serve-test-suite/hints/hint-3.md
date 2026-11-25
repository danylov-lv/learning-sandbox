Concrete workflow for driving each checkpoint to green, plus what CP3
actually wants from you.

1. Run `uv run python 07-capstone-scrape-to-serve-test-suite/tests/validate_cp1.py`
   after every few tests you add, not just once at the end. The output
   tells you exactly which mutant ids survived (never what bug they
   contain -- that's the point). If `m03` survives, go re-read the
   parser docstrings in `src/impl.py` with fresh eyes and ask "what
   input would make a subtly-wrong parser disagree with the correct one,
   that none of my current tests exercise?" -- then add exactly that
   test, rather than adding many more unrelated ones and hoping.

2. Before running `validate_cp2.py` for the first time, confirm Docker
   Desktop is actually running (`docker info` from a terminal). The
   first run will be slow (pulling `postgres:16` / `redis:7` images if
   they are not already cached locally); subsequent runs reuse the
   cached images and only pay real container-startup time, still a few
   seconds per `pytest` subprocess. `validate_cp2.py` spawns one such
   subprocess per mutant plus one baseline run, so a full pass taking a
   couple of minutes is normal, not a sign something is wrong.

3. If a CP2 run times out or hangs rather than cleanly failing, check
   that your tests are not leaving a connection open or a transaction
   uncommitted in a way that blocks the next fixture teardown -- the
   `conn` / `redis_client` fixtures in `conftest.py` already handle
   close/flush for you per test, so this usually means a test is doing
   something outside those fixtures (e.g. opening its own extra
   connection and never closing it).

4. `DESIGN.md` is not busywork -- write it AFTER you have actually seen
   mutants survive and fixed your suites, so the "Where mutation testing
   found gaps" section can describe something real: which mutant id
   category (parser vs. repo vs. cache vs. API -- described by class,
   not by spoiler content) exposed a gap, and what assertion you added.
   `validate_cp3.py` checks for placeholder text (`[fill in`, `TODO`)
   and a minimum length per section, but the actual bar is "would this
   paragraph mean anything to someone who has not read this task's
   spoilers" -- write it like you're handing this suite off to a
   teammate before the refactor, because that's the backstory.

5. Run `validate_cp3.py` last. It re-runs `validate_cp1.py` and
   `validate_cp2.py` as fresh subprocesses -- if either one is not
   independently green when run on its own from the module root, CP3
   cannot pass either, so debug via the individual CP1/CP2 validators
   first rather than staring at CP3's output.
