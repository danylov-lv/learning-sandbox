# Hint 2

The specific mechanisms:

**Corrupt-record capture.** `spark.read.option("mode", "PERMISSIVE").option("columnNameOfCorruptRecord", "_corrupt_record").json(path)` — in PERMISSIVE mode, unparseable lines become rows where every data column is null and the corrupt-record column holds the raw line text. (You must ensure the column actually materializes in the schema — with schema inference it appears only if corrupt records exist; that's fine here, but check `df.columns` before referencing it, or supply an explicit schema that includes it.)

**The gotcha.** `df.filter(col("_corrupt_record").isNull())` straight after `read.json` raises an `AnalysisException` in Spark 3.x: referencing only internal corrupt-record data without any real columns is disallowed because the parser might not even run. The exception text itself suggests the fix — `df.cache()` (materialize) before filtering, then filter, then `.drop("_corrupt_record")`.

**Duplicates.** After dropping corrupt rows: `.dropDuplicates()` with no argument deduplicates on all columns, which for byte-identical input lines means exactly the repeated-line cleanup you want. `distinct()` is equivalent here. Do it *after* dropping the corrupt column, or two different corrupt lines will keep two all-null rows from colliding.

**Partition-scoped overwrite.** Because the DAG writes one day to that day's explicit path, `df.write.mode("overwrite").parquet(f"{SILVER_ROOT}/dt={dt}")` is already partition-scoped: overwrite semantics apply to the target path only, and other `dt=` prefixes are untouched. (The alternative — writing to the table root with `.partitionBy("dt")` and `spark.sql.sources.partitionOverwriteMode=dynamic` — also works but adds a column you'd have to inject and a config you'd have to justify. Know that it exists; you don't need it here.)

**Fail on missing input.** `spark.read.json` on a nonexistent path raises an `AnalysisException` (PATH_NOT_FOUND) on its own — but only at an action/inference. An explicit `os.path.exists` check with a `raise` at the top of the task is clearer and fails faster.

**Day into the task.** Same as task 04: pass `"{{ ds }}"` into the TaskFlow-decorated task, or pull the logical date from the task context.
