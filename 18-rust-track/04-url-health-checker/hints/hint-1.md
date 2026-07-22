This task is really two separate, smaller problems wearing one trench
coat: "read one HTTP response off a socket" and "run N of those at once
without letting more than a fixed number run at the same time." Solve
them one at a time, and test the first one against a single URL before
you ever think about threads.

For the HTTP half: you already know what an HTTP response looks like from
the outside (every browser dev-tools panel shows you one) -- the only new
part is that nobody hands it to you pre-parsed. A `TcpStream` is just a
byte stream, no different in kind from a file. Whatever you'd reach for to
read a file line-by-line-until-a-blank-line, then a fixed number of bytes
after that, is what you reach for here too.

For the concurrency half: don't design your own thread-pool abstraction
from scratch in your head. This is the textbook "bounded worker pool,
shared work queue, results flow back through a channel" pattern -- if
you've never built one, that phrase alone (not this task's specifics) is
worth searching for and reading about before you write anything. The
`worker_count` cap isn't something you enforce by checking a number
somewhere -- it falls out for free from how many threads you actually
spawn.

Don't reach for a crate to do either half for you (there isn't one on
this module's dependency list that could, and that's on purpose) -- both
halves are meant to be small enough to write and understand completely.
