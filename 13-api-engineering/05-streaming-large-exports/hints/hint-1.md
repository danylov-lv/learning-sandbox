Before touching `StreamingResponse` at all, trace the naive version
line by line and ask: at the moment the first byte could theoretically go
out to the client, how much of the result set is already sitting in Python
memory?

```python
rows = cur.execute("SELECT ... FROM shop.products ...").fetchall()
body = "\n".join(json.dumps(row) for row in rows)
return Response(body, media_type="application/x-ndjson")
```

`fetchall()` runs before the function even reaches the `"\n".join(...)`
line. Whatever `StreamingResponse` you wrap around this later, that call
already happened -- the database driver already pulled every matching row
across the wire into a Python list before your handler does anything else.
No generator, no chunked response, no async trick downstream of that line
changes what already occurred upstream of it.

So the real question isn't "how do I stream a response" -- FastAPI/Starlette
already give you that machinery for free. It's "which of the three layers in
this chain (Postgres driver -> Python generator -> HTTP response) is
actually lazy right now, and which ones only look lazy because they're
wrapped in something that sounds streaming?" Check each layer in isolation:
does the driver call return control after fetching ONE row, or after
fetching ALL matching rows? Does your generator function's body run to
completion before its first `yield`, or does it suspend at the first one?
Does the response object write bytes to the socket as they're produced, or
does it wait for something else to finish first?

Only one of those three is actually the bottleneck in the naive version.
Find it before deciding what to change.
