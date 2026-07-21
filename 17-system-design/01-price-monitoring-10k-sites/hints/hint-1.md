# Hint 1

Start from the design doc, not the code. Every hostile-review question
in `HOSTILE-REVIEW.md` is pointing at a real weak point in a naive
version of this design -- read all eight before you write a single
section of `DESIGN.md`, because knowing they're coming should change
how you write "Architecture" and "Scheduling and freshness" the first
time.

For the capacity model: three separate rate concepts are at play here
and it's easy to blur them together -- the rate of *scheduled checks*
(driven by the tiers and their intervals), the rate of *fetch attempts*
(driven by checks plus retries), and the rate the *fleet must be sized
for* (driven by peak, not average). Keep these three straight before
you write any arithmetic.
