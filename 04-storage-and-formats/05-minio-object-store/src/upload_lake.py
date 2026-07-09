"""Upload a local dataset tree to MinIO (S3-compatible), preserving relative paths.

Walks local_dir recursively and uploads every regular file found under it,
using the file's path relative to local_dir, joined onto prefix, as the
object key:

    local_dir=data/lake, prefix="lake/"
    data/lake/month=2025-01/part-0.parquet -> key "lake/month=2025-01/part-0.parquet"

Object storage has no directories — the "month=2025-01/" segment is just
characters inside a flat key, not a real path component. Do not try to
"create" it; simply build the right key string per file.

Endpoint and credentials come from harness.common: minio_endpoint(),
S3_ACCESS_KEY, S3_SECRET_KEY. bucket and prefix are passed in by the caller
(tests/bench.py), not hardcoded here.

Concurrency requirement: uploads must happen through a bounded worker pool
(e.g. concurrent.futures.ThreadPoolExecutor with a fixed max_workers), not
one PUT after another. data/lake-trap has thousands of small files; issuing
their uploads serially means paying each PUT's full network round-trip
before starting the next one, which is the exact bottleneck this task exists
to make visible. A bounded pool overlaps those round trips instead.

boto3 clients are not guaranteed thread-safe for arbitrary reuse patterns
across threads in every botocore version pinned by this module — construct
one client per worker thread (or otherwise ensure each concurrent upload
uses its own client / session) rather than sharing a single client instance
across threads without care.
"""

from pathlib import Path


def upload(local_dir: Path, bucket: str, prefix: str) -> int:
    """Upload every file under local_dir to bucket, keyed by prefix + relative path.

    Args:
        local_dir: local directory to walk recursively (e.g. data/lake).
        bucket: destination S3 bucket name.
        prefix: key prefix to join onto each file's path relative to local_dir
            (e.g. "lake/" so data/lake/month=2025-01/part-0.parquet uploads to
            key "lake/month=2025-01/part-0.parquet").

    Returns:
        Number of objects uploaded.
    """
    raise NotImplementedError("implement upload: concurrently PUT every file under local_dir to bucket/prefix")
