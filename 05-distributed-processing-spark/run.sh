#!/usr/bin/env bash
# Canonical way to run a Spark job inside the module-05 container.
# Usage: ./run.sh <path-to-script-relative-to-this-dir> [spark-submit args after --]
set -euo pipefail
SCRIPT="$1"
shift || true
MSYS_NO_PATHCONV=1 docker compose exec spark /opt/spark/bin/spark-submit \
  --master "local[*]" \
  --driver-memory 6g \
  --conf spark.jars.ivy=/opt/spark-ivy \
  --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
  --conf spark.hadoop.fs.s3a.endpoint=http://minio:9000 \
  --conf spark.hadoop.fs.s3a.path.style.access=true \
  --conf spark.hadoop.fs.s3a.access.key=sandbox \
  --conf spark.hadoop.fs.s3a.secret.key=sandbox123 \
  --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \
  --conf spark.hadoop.fs.s3a.connection.ssl.enabled=false \
  "/workspace/$SCRIPT" "$@"
