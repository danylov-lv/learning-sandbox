# Hint 3 — concrete approach

`src/benchmark.sh`, run from the module root, needs one line along the
shape of:

```
hyperfine --warmup <N> --export-json 04-hyperfine-benchmark/results.json \
  "<fd command counting .log files under data/filetree>" \
  "<rg command counting .log files under data/filetree>"
```

Pick `<N>` generously enough to prime the filesystem cache for both
commands equally (a handful is plenty for a tree this small). After it
runs, either read the printed terminal summary (hyperfine tells you
directly which one it thinks was faster and by what ratio) or open
`results.json` and compare the two `mean` fields yourself — then transfer
whichever is actually lower into `ANSWER.md`'s `Winner:` line as `A` or
`B` matching the command's position on your `hyperfine` line, and its
ratio into `Relative:`.
