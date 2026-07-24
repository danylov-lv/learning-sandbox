# Hint 2 — mechanism

- `parallel [options] 'command template' ::: input1 input2 ...` — the
  shell glob `data/batch/inputs/*.json` can sit directly after `:::` and
  expands before `parallel` ever sees it.
- `{}` in the template is replaced with the whole input path;
  `{/}` is replaced with just its basename (filename, keeping the
  extension) — that's what lets the output filename match the input
  filename without you constructing it by hand.
- Redirecting (`> data/batch/outputs/{/}`) inside the quoted command
  template works exactly like it would in a plain shell command — each
  parallel job gets its own redirection target because `{/}` differs per
  job.
- `--jobs N` bounds how many of those run concurrently; `--joblog FILE`
  writes one row per job (command, exit code, timing) to `FILE` regardless
  of `--jobs`.
