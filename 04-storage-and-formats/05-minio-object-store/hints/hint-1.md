# Hint 1

An object store bucket is a flat namespace of keys, not a filesystem tree.
"Uploading a directory" is a concept your client invents by walking the
local filesystem and issuing one `PUT` per file — the store itself has no
notion of directories, mkdir, or rename. Everything you do with
`data/lake-trap`'s thousands of tiny files has to go through that same
one-`PUT`-per-object model, and each `PUT` is a full network round trip to
MinIO, not a cheap syscall like writing a local file.

Think about what that means for throughput. If you upload strictly one file
after another — issue the request, wait for the response, then issue the
next — your total time is roughly (number of files) x (round-trip latency),
no matter how fast each individual upload actually is once it starts. That
math gets ugly fast once file count reaches the thousands. What would let
you pay for many round trips at once instead of one after another?

Also spend a few minutes with the MinIO console (`http://localhost:9302`,
`sandbox`/`sandbox123`) or a manual `list_objects_v2` call before writing
any code. Notice that a bucket listing comes back in pages, capped at 1000
keys each — "list everything under this prefix" is not one API call once
you have more than 1000 objects under it.
