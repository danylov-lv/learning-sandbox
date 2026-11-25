# Recon writeup

Fill in each section below after building your crawler, describing what you
actually observed against the running target -- not general theory. The
validator checks that all four headings are present, that no `[fill in`
placeholder remains, that each section has real content, and that you
mention each defense concretely (honeypots, the rate limit, the header gate,
the JS-only endpoint).

## Header/fingerprint gate

[fill in: what happens to a request with no/wrong headers, exactly which
headers the target inspects, and what you had to send to get through. Is
there any TLS/JA3 component, or is it header-only?]

## Rate limiting

[fill in: how you discovered the rate limit's rough shape (what a fast burst
does, what status code and header come back), and how you paced your client
so it was never banned. Did a bounded-concurrency semaphore alone work on
this target? Why or why not?]

## Honeypots

[fill in: where the trap links hide, what markup signals distinguish them
from real product links, whether real product pages ever link to them, and
what `robots.txt` says. How did you exclude them before fetching?]

## JS-only fields

[fill in: which fields never appear in the HTML detail page, where they do
live, and why fetching that source is modeled as more expensive than a plain
HTML fetch.]
