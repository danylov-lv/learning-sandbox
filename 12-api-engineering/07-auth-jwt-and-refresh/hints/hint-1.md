Start by separating three concerns that are easy to blur together into one
"auth" blob: **issuing** a token, **verifying** a token, and **tracking
state about refresh tokens**. Almost every classic JWT bug lives on the
verification side, not the issuing side -- it's easy to write correct code
that mints a token, and much easier to accidentally write verification
code that's more permissive than you think.

Ask yourself, concretely, for `/me`: given a string that arrived in an
`Authorization` header, what EXACTLY does your code need to be true before
it trusts the `sub` claim inside it? Write that list out. A signature
matching some key isn't enough on its own -- which key, matching which
algorithm, matching which claim values? Every trap in `tests/traps.py` is
aimed at exactly one item falling off that list.

For the refresh side, ask a different question: a JWT's signature can tell
you "this token was legitimately issued by me at some point." It cannot
tell you "and nobody has used it yet" -- that's not something a signature
can express, because the token itself doesn't change when it gets used.
If "has this specific refresh token already been spent" needs to be
knowable, where does that fact have to live?

The next hint gets into the specific library mechanics (pyjwt's decode
options, exception hierarchy) and one reasonable shape for the state a
rotating refresh token needs.
