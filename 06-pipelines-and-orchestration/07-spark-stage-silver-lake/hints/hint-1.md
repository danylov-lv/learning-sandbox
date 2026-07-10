# Hint 1

Start from `dags/smoke_env.py` — its `check_spark` task is a working SparkSession with s3a against this stack's MinIO. Your job is that, plus three ideas:

1. Spark's JSON reader has *modes* for handling records it can't parse, and a way to keep the evidence instead of silently nulling bad lines. The docs for the JSON data source list both. The default mode is already more forgiving than you might expect — the question is how you *see* which rows were bad.

2. When you try to filter on that evidence immediately after reading, recent Spark versions refuse with a fairly explicit `AnalysisException`. Read the error message fully — it tells you what to do. Understand *why* before applying the fix: what would it mean to query only the corrupt-record column when parsing is lazy?

3. "Overwrite this day's partition, touch nothing else" can be had in more than one way: writing directly to the partition path with overwrite mode, or writing to the table root with partitioning and the right overwrite setting. One of them is much simpler for this task's layout. Think about what `s3a://lake-06/silver/prices/dt=<ds>/` being the *full* target path implies.

For the write-up: you built the embedded-local variant, so argue from what you actually observed — where do the driver and executors live, whose memory do they eat, what happens to the scheduler container while your job runs, and what would break first at 10x.
