# Hint 3

Concrete approach, close to pseudocode. You still have to turn every step
below into working Rust yourself.

## `parse_line`

```text
1. ip_end = line.find(' ') -> MissingField("ip") if None
   ip = &line[..ip_end]
   validate ip looks like a dotted-quad: split on '.', require exactly 4
   pieces, each piece non-empty and made only of ASCII digits
   -> MissingField("ip") if that check fails (see the module doc comment's
   "trap" section for why this check matters, not just a nice-to-have)

2. bracket_open = line.find('[') -> MissingField("timestamp open bracket")
   bracket_close = line[bracket_open..].find(']') -> MissingField("timestamp close bracket")
   timestamp = &line[bracket_open + 1 .. bracket_open + bracket_close]

3. first_quote = line[bracket_open + bracket_close..].find('"') -> MissingField("request quote open")
   (translate that back into an absolute offset into `line`)
   second_quote = search for the NEXT '"' after first_quote -> MissingField("request quote close")
   request = &line[first_quote + 1 .. second_quote]   // e.g. "GET /api/products HTTP/1.1"

4. split `request` on whitespace; take the 1st token as method, 2nd as path
   -> MissingField("method") / MissingField("path") if either is absent

5. the remainder of `line` after the request's closing quote holds:
   status, bytes, a "-" referrer, a quoted user-agent, and the response time.
   You don't need to parse the referrer or the user-agent's *contents* --
   you only need to walk past them correctly to reach status/bytes (which
   come right after the request's closing quote) and the response time
   (the last whitespace-separated token on the line).
   status_str.parse::<u16>()?  (this is where InvalidInteger gets exercised)
   bytes_str.parse::<u64>()?
   response_time_str.trim().parse::<f64>()?  (InvalidFloat)

6. build and return Ok(LogEntry { ip, timestamp, method, path, status, bytes, response_time_ms })
```

A line with the brackets stripped fails at step 2. A line with the status
replaced by `"UNKNOWN"` fails at step 5's integer parse. A truncated line
fails wherever the missing tail was needed. A line with quotes stripped
fails at step 3 (no closing quote to find). A line with a trailing garbage
token corrupts whatever you treat as "the last token" in step 5, so it
fails the float parse there. You do not need a special branch per
corruption mode -- each one naturally breaks a different step of the
happy path.

## `aggregate`

```text
stats = LogStats::default()
for line_result in reader.lines():
    line = line_result.expect(...)   // an io::Error here is a real I/O
                                      // failure, not a malformed log line --
                                      // decide whether that should panic or
                                      // propagate; it's not what
                                      // malformed_lines counts
    stats.total_lines += 1
    match parse_line(&line):
        Ok(entry) =>
            stats.well_formed_lines += 1
            *stats.status_class_counts.entry(status_class(entry.status)).or_insert(0) += 1
            *stats.method_counts.entry(entry.method.to_string()).or_insert(0) += 1
            *stats.path_counts.entry(entry.path.to_string()).or_insert(0) += 1
            track entry.ip in a HashSet<String> (or count distinct IPs some other way)
            if entry.status >= 500: bump a running 5xx counter
            push entry.response_time_ms into a Vec<f64>
        Err(_) =>
            stats.malformed_lines += 1

after the loop:
    stats.unique_ips = the HashSet's length
    stats.error_rate_5xx = five_xx_count as f64 / stats.well_formed_lines as f64 (guard divide-by-zero)
    sort the response-time Vec, then fill in stats.response_time_stats using percentile() and a plain mean
```

Note that `entry.method.to_string()` / `entry.path.to_string()` *do*
allocate -- and that's fine. The "borrow, don't allocate" rule from the
module doc comment is about `parse_line` and `LogEntry`, which run once
per line and must not allocate a fresh `String` just to hand you back a
field that already exists in `line`. `HashMap<String, u64>` needs owned
keys to outlive the loop iteration that created them, so allocating
exactly once per *distinct key insertion* (not once per line) at the
aggregation step is the correct, unavoidable cost -- a different problem
from the one `LogEntry`'s lifetime is solving.

## `percentile`

```text
if sorted_ascending.is_empty(): return 0.0
idx = (p * (sorted_ascending.len() - 1) as f64).round() as usize
return sorted_ascending[idx]
```

## `top_paths`

```text
collect (path.clone(), *count) pairs out of the HashMap into a Vec
sort the Vec by: count descending, then path ascending as the tiebreak
  (a two-key sort_by with a `.then_with(...)` chained comparator)
truncate to n
```
