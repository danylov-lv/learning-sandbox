# Hint 1 -- direction

Start with why `POST /exports` can't just compute the aggregate and return
it. It's not (only) about speed -- it's about what "the client shouldn't
block" actually forces on your design: the moment you return a response, the
work either hasn't started, is in progress, or is done, and the CLIENT has
no way to know which. So the response has to be a promise ("here's an id,
ask me later"), and something ELSE -- outside the request/response cycle
that's already finished -- has to be doing the work and recording where it
got to.

That "something else" needs a place to put its progress that isn't just a
Python variable in the handler's stack frame -- that frame is gone the
instant the response is sent. `GET /exports/{job_id}` is a SEPARATE request,
quite possibly served by different code running at a different moment; the
only thing connecting it to the POST that created the job is whatever both
of them can see: a durable row, in Postgres, that the POST created and the
background work updates in place.

That's the "enqueue and poll" half, and it's mostly plumbing (FastAPI gives
you two ways to run something after the response starts: `BackgroundTasks`,
which Starlette runs after the response has been sent, or a bare
`asyncio.create_task(...)` you manage yourself). Neither is hard once you
see the shape.

The actual hard part is the OTHER half: what happens when the SAME POST
arrives twice -- or twenty times, all at once, before any of them has had a
chance to write anything. Read the request handler you're about to write and
ask: if twenty copies of it run at literally the same instant, is there a
moment where each one reads some state, decides "nothing exists yet, I'll
create it," and then writes -- with the read happening before ANY of the
twenty writes? If so, all twenty will make that same decision, and you'll
get twenty jobs for what should be one. This is the exact race task 03's
rate limiter had, aimed at a different kind of state (a job record instead
of a counter) -- the fix is the same shape: don't let "check" and "act" be
two separate, interruptible steps.
