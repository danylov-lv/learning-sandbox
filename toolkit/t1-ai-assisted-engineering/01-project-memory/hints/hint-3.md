No ready-made CLAUDE.md here — just how to check your own draft before you
consider it done.

**Read it as if you'd never seen this project.** Could you run the tests
from your own "Commands" section without already knowing the answer? Does
your "Architecture" section actually tell you where `parse_price` lives,
or does it just restate that the project "parses prices"?

**Ground every claim in a specific thing you read.** For "Conventions",
you should be able to point at the exact line in
`src/priceparser/__init__.py` that backs each bullet — the money
representation, the `None`-on-failure contract, the currency-code
normalization. If a bullet could apply to literally any Python project
unchanged, it's too generic to be worth memory space; either sharpen it
to this project's specific choice, or cut it.

**"What NOT to do" should name real, specific temptations.** Look at
`parse_price`'s regex and its currency handling — what's the version of
this function a less careful pass would write, and why would it be wrong
for this specific codebase's contract (not wrong in general)?

**For "Memory vs rot," answer concretely, not just in the abstract.**
Pick at least one specific kind of fact you are choosing NOT to put in
this CLAUDE.md, and say why — tie it to something about this exact
project (e.g. something in sample-project's README that you deliberately
did not copy in verbatim, and why copying it would have been the wrong
call for a memory file specifically, as opposed to documentation in
general).
