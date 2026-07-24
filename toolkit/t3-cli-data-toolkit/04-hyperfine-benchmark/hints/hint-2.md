# Hint 2 — mechanism

- `hyperfine --warmup N --export-json <path> "command A" "command B"` is
  the whole shape. `--warmup` runs (and discards) N executions before the
  timed ones begin.
- Quote each command as one shell-escaped string. On Windows, hyperfine
  runs each one through `cmd.exe` by default, so anything with a glob
  pattern needs double quotes, not single quotes, around the pattern
  itself.
- Piping to `wc -l` inside a benchmarked command works fine as long as
  `wc` resolves on `PATH` for whichever shell hyperfine is invoking
  through.
- The two things to count with: `fd`'s dedicated extension filter
  (`-e log`) vs `rg`'s file-listing mode restricted by a glob
  (`--files -g "*.log"`), both rooted at `data/filetree`.
