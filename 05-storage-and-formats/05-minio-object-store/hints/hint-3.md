# Hint 3

Concrete shape for `upload()`:

1. Build the S3 client once, outside the concurrent part, using
   `boto3.client("s3", endpoint_url=..., aws_access_key_id=..., aws_secret_access_key=..., region_name="us-east-1")`.
   `endpoint_url` comes from `harness.common.minio_endpoint()` (it already
   includes the `http://` scheme, unlike `pyarrow.fs.S3FileSystem`'s
   `endpoint_override`, which wants the host:port without a scheme — that
   distinction matters if you ever mix boto3 and pyarrow S3 code, though
   this task only asks you to write with boto3). Credentials are
   `harness.common.S3_ACCESS_KEY` / `S3_SECRET_KEY`. `region_name` can be
   anything non-empty; MinIO ignores it but boto3 wants it set.

2. Walk `local_dir` with `Path(local_dir).rglob("*")`, filter to files only
   (skip directories), and for each file compute its key as
   `prefix + relative_path.as_posix()` where `relative_path` is the file's
   path relative to `local_dir` — `.as_posix()` gives you forward slashes
   even on Windows.

3. Push the list of (local_path, key) pairs through a
   `concurrent.futures.ThreadPoolExecutor(max_workers=N)` (try N somewhere
   in the 16-64 range and see what changes), submitting one
   `client.upload_file(str(local_path), bucket, key)` call per file (or
   `put_object` with an open file handle, if you want to control the
   read yourself — `upload_file` is simpler and handles multipart for you
   if a file happens to be large). Use `as_completed` or `executor.map` to
   drain the futures and count successes; let an exception from any one
   upload propagate (don't swallow failures silently).

4. If you want one client shared across all worker threads, pass a
   `botocore.config.Config(max_pool_connections=N)` (N >= your worker
   count) when constructing it, so the HTTP connection pool isn't the
   bottleneck. The simpler alternative — construct a fresh client per
   worker thread via a thread-local or inside the submitted function — sidesteps
   the question entirely at the cost of one extra client object per thread.

5. Return the count of files uploaded (should equal the count you queued,
   assuming nothing raised).

`tests/bench.py` calls `upload(data/lake, "price-lake", "lake/")` and
`upload(data/lake-trap, "price-lake", "lake-trap/")` — your function doesn't
need to know which dataset it's uploading, only how to walk a directory and
push files under a prefix.
