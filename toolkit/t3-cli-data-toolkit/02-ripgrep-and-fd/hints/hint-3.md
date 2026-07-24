# Hint 3 — concrete approach

- **Q1**: `rg` with `-o` (only matching), a capture-group replacement via
  `-r`, searched recursively under the `logs/` subdirectory only. Dedup
  and sort the resulting codes, then join them with commas and no
  trailing newline before the next marker.
- **Q2**: `fd` in glob mode against pattern `*.config.json`, rooted at
  `data/filetree`, with `vendor` passed to `--exclude`. `fd` prints
  absolute or search-root-relative paths depending on how you invoke it —
  make sure what you print is relative to `data/filetree` specifically
  (not to your current shell directory) and uses `/` separators.
- **Q3**: `rg -o -P` for the lookahead pattern, rooted at
  `data/filetree/src`, no `--no-filename` needed since you're only
  counting — pipe the match list through `wc -l` (each output line is one
  match, since `-o` prints one match per line).
- **Q4**: five separate `fd -e <ext> . data/filetree | wc -l` calls (or
  one pass that classifies every file by its suffix), printed as
  `ext:count` lines in alphabetical order: `js`, `json`, `log`, `md`,
  `py`.
