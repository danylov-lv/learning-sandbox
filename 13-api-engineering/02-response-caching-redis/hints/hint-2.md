The pattern is **cache-aside** (also called lazy loading). The GET handler
follows a fixed five-step shape:

1. Build the cache key for this `category_id`.
2. Ask Redis for that key (`GET`).
3. **Hit** -- Redis returned something: that's your answer. Return it and mark
   the response as a HIT. Do not query Postgres at all on this path.
4. **Miss** -- Redis returned nothing: compute the summary from Postgres
   (`SELECT count(*), sum(price), avg(price) FROM shop.products WHERE
   category_id = ...`), then STORE it in Redis before returning, and mark the
   response as a MISS.
5. When you store on a miss, set the TTL in the SAME operation that sets the
   value -- Redis has a command for "set this key to this value AND expire it
   in N seconds" so there is never a window where the key exists without an
   expiry.

The invalidate handler is just step-2's key with a delete instead of a get.

Two design questions the miss path forces you to answer, both left for
hint-3:

- Redis stores strings/bytes, not Python dicts. What exactly do you put in
  the value, and how do you make sure the HIT path reconstructs the *same
  bytes* the MISS path sent (the validator checks the two bodies are
  identical)?
- How do you attach the `X-Cache: HIT|MISS` header to the response? FastAPI
  gives you more than one way; the one that also lets you control the exact
  response bytes is the one that makes the byte-identical requirement easy.
