pyarrow's `pyarrow.parquet.write_table` (and `ParquetWriter`) accept `compression=` and, for zstd specifically, `compression_level=`. `compression` can be a single string applied to every column, or a dict mapping column name to codec if you want to compress some columns differently from others (not required here, but worth knowing it exists — Parquet compression is applied per column chunk, not once for the whole file).

`compression="none"` is a real, valid value — it disables codec compression but Parquet still applies its own encodings (dictionary, RLE) underneath, so "none" is not the same as "raw bytes of the values."

To check what actually got written, don't trust your own kwargs — read them back: `pyarrow.parquet.ParquetFile(path).metadata.row_group(0).column(i).compression` tells you the codec pyarrow actually used for that column chunk. The validator does exactly this. If you pass an unsupported combination silently, some pyarrow versions won't error, they'll just ignore it — verify, don't assume.

For streaming, look at how you'd build one `pyarrow.RecordBatch` (or small `pyarrow.Table`) per chunk of a few tens of thousands of JSONL lines, with an explicit schema (don't let pyarrow infer types row by row — infer once, apply consistently, especially for the nullable `price`/`in_stock` columns on non-200 rows).
