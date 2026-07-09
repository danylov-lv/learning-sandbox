# Hint 2

The stock claim query picks its candidate rows with `ORDER BY id LIMIT n
FOR UPDATE`. `FOR UPDATE` takes a row lock on every row the query touches
before returning it. If another session already holds a lock on the first
row in that order, this session doesn't skip past it and take the next
available row instead — it blocks, waiting for that specific row's lock to
be released, before it can even finish evaluating which rows to return.

Now think about what "id order" means across N concurrent workers, all
claiming from the same small pool of `status = 'pending'` rows: they don't
pick different starting points. They all try to lock the *same* leading
rows, in the *same* order, at roughly the *same* time. What does that do
to the second, third, fourth... worker to reach that row?

Separately: in this harness, the simulated provider API call happens
*before* the claim transaction commits, not after. Why would that make
the lock-holding time of each claim matter so much more than if the commit
happened immediately after the `UPDATE`?
