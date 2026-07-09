# Hint 1

Separate the things that change from the things that just happen.

Shops and products have current state (a name, a tier, a brand) that gets
overwritten by later admin events — that's mutable, entity-like data. Price
observations are different: once a scrape records a price at a point in
time, that fact never changes. It just accumulates. Modeling both the same
way (both as rows you `UPDATE`, or both as an infinite append-only log) will
make one half of your schema awkward.

Also think about what makes a price observation unique. The event stream
tells you directly: two observations for the same (shop, product) at the
same `event_time` are the same fact arriving twice, not two different
prices. What does that imply about a natural key?

And a listing — a (shop, product) pair — is neither purely static nor purely
a log entry. It has its own small lifecycle (discovered, delisted,
relisted). Where does that lifecycle live, and how do you answer "is it
active right now" without touching the observation table at all?
