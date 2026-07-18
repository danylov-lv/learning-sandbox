Don't conflate "the network call failed" with "the model gave a bad
answer." They feel similar (both mean `structured()` didn't get a usable
result on the first try) but they need completely different handling: one
is about the TRANSPORT (an exception came out of `generate()` before any
text was even produced), the other is about the CONTENT (`generate()`
returned successfully, but what came back isn't valid JSON, or is valid
JSON that doesn't match what the caller asked for). Keep those two
failure modes, and their two budgets (`max_retries` vs `max_reasks`), as
separate concerns in your head before you write any code.

Think about what a pipeline operator would actually want to know after a
batch job finishes overnight: how many calls did it make in total, how
many of those were retries after a network blip, how many were reasks
after a bad response, how many times did it have to fall back to a second
provider. `.stats` exists to answer exactly those questions -- if you're
not sure where a counter belongs, ask which of those operator questions it
answers.
