# Hint 2 — mechanism

- **Q1**: `rg`'s `-o` prints only the matched text; combined with `-r`
  you can replace the whole match with just the captured group
  (`-r '$1'`). Pipe that through a dedup + sort (`sort -u`) and join with
  commas (`paste -sd,`).
- **Q2**: `fd`'s `-g`/`--glob` flag switches it from regex mode to shell
  glob mode, which is what a literal `*.config.json` pattern needs.
  `-E`/`--exclude` takes a glob too and prunes a whole directory from the
  walk — that's different from filtering matches after the fact with
  something like `grep -v vendor`, and matters here because a filename
  could coincidentally contain "vendor" outside the excluded directory.
- **Q3**: `rg`'s default regex engine (Rust's `regex` crate) does **not**
  support lookaround at all — you need `-P`/`--pcre2` to opt into a
  PCRE2-backed engine that does. Without `-P`, a lookahead pattern is a
  syntax error, not a silently wrong answer.
- **Q4**: `fd -e EXT` filters by extension already split from the
  filename (so it agrees with `path.suffix` semantics on a
  `name.config.json` file: the extension is `json`, not `config.json`).
  Loop it once per extension, or find another way to tally all five in
  one pass — either is fine as long as the final counts are right.
