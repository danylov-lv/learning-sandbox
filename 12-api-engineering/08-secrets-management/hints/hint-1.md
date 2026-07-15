# Hint 1 -- direction

**Half A.** Ask yourself: if you `grep -r` the checked-out files in a repo
right now, what can you possibly find? Only what's *currently there*. But
`git` doesn't forget anything just because a file was deleted and that
deletion was committed -- the old version of that file is still a real
object inside `.git/`, reachable from the commit that added it, forever
(until someone rewrites history, which almost nobody does, because it's
disruptive and most teams don't realize the exposure is still live). So a
scan that only looks at the working tree will always miss "we noticed and
deleted it" -- which is exactly the case a lot of real incident writeups
describe: someone DID clean up, and it didn't help, because cleanup ==
"gone from HEAD", not "gone from the repo". You need two passes: one over
what's checked out now, and a separate one that walks every commit's
snapshot, independent of what HEAD currently looks like.

The other half of Half A is precision, and it's not a smaller concern than
recall -- read the fixture's decoys list in the README again. A public key
is not a secret. A `.env.example` with empty values is not a secret. A
credential that's *documented* as a placeholder (you'll recognize it when
you see it) is not a secret. A file that merely contains a long hex string
is not automatically a secret either -- hashes, commit ids, and build ids
all look like that too. Before you write any detection logic, write down,
in your own words, what actually separates "this is a live credential"
from "this looks like one." That answer is what your heuristics need to
encode.

**Half B.** The stock `service/docker-compose.yml` puts a real value where
a *path* belongs. The fix isn't "encrypt the value" or "put it somewhere
else in the YAML" -- it's a change of kind: the compose file and the
application should only ever see a filesystem path to where the secret
material lives, never the material itself. Go look at how the official
`postgres` Docker image's own entrypoint script handles
`POSTGRES_PASSWORD` vs `POSTGRES_PASSWORD_FILE` -- that's the exact
convention this half asks you to implement on the reading side.
