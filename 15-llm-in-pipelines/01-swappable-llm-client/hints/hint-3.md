No ready-made code -- just the concrete shape, close to pseudocode.

A private helper for the inner layer, something like
`_ask_with_retry(client, prompt, system)`:

```
for attempt in 0 .. max_retries:
    record start time
    try:
        response = client.generate(prompt, system=system, format="json", temperature=0.0)
        record elapsed time into stats["total_latency"]; stats["calls"] += 1
        add approx token count to stats["total_tokens"]
        return response
    except TransientError:
        record elapsed time into stats["total_latency"]; stats["calls"] += 1
        if attempt < max_retries:
            stats["retries"] += 1
            sleep(backoff_base * 2**attempt)
            continue
        raise   # retry budget exhausted -- propagate to the outer layer
    # any other exception type: don't catch it at all, let it propagate
```

A private helper for the outer layer, something like
`_attempt_client(client, prompt, schema, system)`:

```
current_prompt = prompt
for ask in 0 .. max_reasks:
    response = _ask_with_retry(client, current_prompt, system)   # may raise
    try:
        parsed = json.loads(response)
    except ValueError as e:
        error = f"invalid JSON: {e}"
    else:
        error = _validate(parsed, schema)   # None if valid, else an error string
        if error is None:
            return parsed
    if ask < max_reasks:
        stats["reasks"] += 1
        current_prompt = prompt + "\n\n" + describe(error)   # NOT accumulated across reasks
    else:
        raise StructuredOutputError(error)
```

And `structured()` itself:

```
try:
    return _attempt_client(primary, prompt, schema, system)
except Exception:
    if fallback is None:
        raise
    stats["fallbacks"] += 1
    return _attempt_client(fallback, prompt, schema, system)   # let this one's outcome be final
```

`_validate(parsed, schema)`: if `schema` is a `dict`, check `parsed` is a
`dict`, then every name in `schema.get("required", [])` is a key of it,
then every name in `schema.get("properties", {})` that IS present in
`parsed` matches the declared type (remember: `bool` must not satisfy
`"number"` or `"integer"`, since `isinstance(True, int)` is `True` in
Python but a JSON boolean is not a JSON number). If `schema` is callable,
call it and return whatever it returns (or `str(exception)` if it raises)
-- it already speaks the "`None` or error string" protocol directly.

`.stats` as a property: return a fresh `dict(self._stats)` (or equivalent
copy) each time, not the internal mutable dict itself.
