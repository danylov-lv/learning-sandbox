Don't start by asking "how do I make rendering cheaper." You can't -- the
render step's cost is fixed by the cost model. Ask instead: "for how many
products do I actually *need* the render step at all?"

Every product gets a cheap fetch no matter what -- there's no way around
that, it's how you'd learn anything about a product in the first place.
The question is only whether that cheap fetch is ever followed by the
expensive one. A router that renders everything is safe (never misses
data) but wasteful. A router that renders nothing is cheap but misses data
for every product where it mattered.

Somewhere in the cheap page you already fetched is a signal that tells you,
for that specific product, whether the expensive step is going to change
anything at all. Find that signal before you write a single line of
routing logic -- the whole task falls out of it once you have it.
