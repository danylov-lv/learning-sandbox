Read every patch's `PR_DESCRIPTION.md` last, not first -- or at least,
don't let it anchor your read of the code. A plausible PR description is
exactly the thing that makes a plausible-but-flawed patch dangerous: it
tells you what the author BELIEVES the code does, which is not evidence
of what it actually does. Read `code.py` cold, work out its contract
yourself, then check the PR description's claims against that, not the
other way around.

For each patch, ask: what's the exact boundary case, concurrent
scenario, or input shape where this code's actual behavior would diverge
from its obvious/intended behavior? The four patches here are each
built around a different classic category of bug (worth knowing the
categories, not just these four instances): a race between two
concurrent operations, an off-by-one at a slicing/range boundary, and an
implicit type coercion that changes truthiness. One patch has none of
these -- your job includes correctly recognizing that one too, which is
its own skill (false positives waste real review time).

Once you have a verdict, writing the test is a second, separate skill:
a test that would ACTUALLY fail on this exact code, not a test that
merely exercises the function. "I called it and it didn't crash" is not
the same claim as "I asserted the specific behavior that's wrong."
