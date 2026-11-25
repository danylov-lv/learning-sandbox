# Hint 2

The fix for one-PUT-at-a-time uploading is a bounded pool of concurrent
workers, each independently uploading a file and blocking on its own
network round trip while the others proceed. "Bounded" matters on both
ends: too few workers and you're barely better than serial; an unbounded
number and you can overwhelm the connection pool (or MinIO itself) and get
worse throughput, not better, plus you lose any predictability in resource
use. A pool sized somewhere in the tens of workers is a reasonable starting
point for a single-machine client talking to a single endpoint — this is a
knob worth trying a couple of values for and writing down what you saw in
`NOTES.md`, not something to guess once and move on from.

Two things trip people up when they first parallelize S3 uploads with
`boto3`:

- A single `boto3` client is not automatically safe to hammer from many
  threads at once in every version/configuration. Look at how the
  underlying HTTP connection pool is sized (`botocore.config.Config` has a
  `max_pool_connections` option), or give each worker thread its own
  client — either approach avoids threads serializing on a pool that's too
  small to actually run them concurrently.
- Building the key: object storage never has "the current directory," so
  you need to compute each file's key yourself — the file's path relative
  to `local_dir`, with the prefix you were given stuck on the front, using
  forward slashes regardless of what OS you're running on (Windows'
  `Path` separators are backslashes; S3 keys always use `/`).

For the LIST side (which `tests/bench.py` and `tests/validate.py` exercise,
not something you implement): `boto3`'s `list_objects_v2` returns at most
1000 keys and an `IsTruncated` / `NextContinuationToken` to fetch the next
page. `client.get_paginator("list_objects_v2").paginate(...)` handles the
pagination loop for you and is what the harness uses to count pages.
