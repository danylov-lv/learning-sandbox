Prose sketches close to pseudocode. You still have to write and debug the
actual Rust -- nothing here is copy-pasteable.

## `looks_like_timestamp`

```
fn looks_like_timestamp(s: &str) -> bool {
    let b = s.as_bytes();
    if b.len() != 20 { return false; }
    let digit = |i| b[i].is_ascii_digit();
    // positions 0-3 digit, 4 is '-', 5-6 digit, 7 is '-', 8-9 digit,
    // 10 is 'T', 11-12 digit, 13 is ':', 14-15 digit, 16 is ':',
    // 17-18 digit, 19 is 'Z' -- chain these with && into one bool
}
```

## `parse_row`

```
fn parse_row(line: &str) -> Result<ProductRow, RowParseError> {
    let fields: Vec<&str> = line.split(',').collect();
    if fields.len() != 6 { return Err(RowParseError::WrongFieldCount(fields.len())); }
    let (id_s, sku_s, category_s, price_s, in_stock_s, scraped_at_s) = (fields[0], .., fields[5]);

    let id: i64 = id_s.parse()?;                 // ParseIntError -> InvalidId via `?`
    if sku_s.is_empty() { return Err(RowParseError::EmptySku); }
    let price: f64 = price_s.parse()?;           // ParseFloatError -> InvalidPrice via `?`
    if price <= 0.0 { return Err(RowParseError::NonPositivePrice(price)); }
    let in_stock = match in_stock_s {
        "true" => true,
        "false" => false,
        other => return Err(RowParseError::InvalidBool(other.to_string())),
    };
    if !looks_like_timestamp(scraped_at_s) {
        return Err(RowParseError::InvalidTimestamp(scraped_at_s.to_string()));
    }

    Ok(ProductRow { id, sku: sku_s.to_string(), category: category_s.to_string(), price, in_stock,
                    scraped_at: scraped_at_s.to_string() })
}
```

## `parse_rows`

```
fn parse_rows<R: BufRead>(reader: R) -> impl Iterator<Item = Result<ProductRow, RowParseError>> {
    reader.lines()
        .map(|line| line.expect("reading a line from an already-opened file"))
        .map(|line| parse_row(&line))
}
```

That's the whole function -- if yours is much longer, you're probably
doing something `parse_row` should already be doing.

## `build_column`

```
fn build_column<T: ArrowColumn>(name: &str, values: impl Iterator<Item = T>) -> (Field, ArrayRef) {
    let mut builder = T::Builder::default();
    for value in values {
        T::append(&mut builder, &value);
    }
    (Field::new(name, T::arrow_data_type(), false), builder.finish())
}
```

## `write_products_parquet`

```
fn write_products_parquet(csv_path, parquet_path, row_group_size) -> Result<ConversionStats, PipelineError> {
    let file = File::open(csv_path.as_ref())?;
    let mut reader = BufReader::new(file);
    let mut header = String::new();
    reader.read_line(&mut header)?;             // discard exactly the header line

    let (mut ids, mut skus, mut categories, mut prices, mut in_stocks, mut scraped_ats) = (vec![], vec![], vec![], vec![], vec![], vec![]);
    let mut stats = ConversionStats::default();
    for result in parse_rows(reader) {
        stats.total_rows += 1;
        match result {
            Ok(row) => {
                stats.valid_rows += 1;
                ids.push(row.id); skus.push(row.sku); categories.push(row.category);
                prices.push(row.price); in_stocks.push(row.in_stock); scraped_ats.push(row.scraped_at);
            }
            Err(_) => stats.dirty_rows += 1,
        }
    }

    let (id_f, id_a) = build_column::<i64>("id", ids.into_iter());
    let (sku_f, sku_a) = build_column::<String>("sku", skus.into_iter());
    let (cat_f, cat_a) = build_column::<String>("category", categories.into_iter());
    let (price_f, price_a) = build_column::<f64>("price", prices.into_iter());
    let (stock_f, stock_a) = build_column::<bool>("in_stock", in_stocks.into_iter());
    let (ts_f, ts_a) = build_column::<String>("scraped_at", scraped_ats.into_iter());

    let schema = Arc::new(Schema::new(vec![id_f, sku_f, cat_f, price_f, stock_f, ts_f]));
    let batch = RecordBatch::try_new(schema.clone(), vec![id_a, sku_a, cat_a, price_a, stock_a, ts_a])?;

    let props = WriterProperties::builder()
        .set_compression(Compression::SNAPPY)
        .set_max_row_group_row_count(Some(row_group_size))
        .build();

    let out = File::create(parquet_path.as_ref())?;
    let mut writer = ArrowWriter::try_new(out, schema, Some(props))?;
    writer.write(&batch)?;
    writer.close()?;

    Ok(stats)
}
```

The `?` operator working across three different error sources (`io::Error`
from the `File`/`BufReader` calls, `ArrowError` from `RecordBatch::try_new`,
and whatever `ArrowWriter`'s methods return) inside one function is only
possible because `PipelineError` already has a `From` impl for each of
them -- that's the entire point of writing those three `impl From` blocks
before touching this function.
