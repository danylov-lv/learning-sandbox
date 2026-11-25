# Hint 3 -- concrete approach, still no ready code

**Half A shape.** Two passes, then merge:

1. *Worktree pass.* Walk `repo_path` with something like
   `Path.rglob("*")`, skipping the `.git/` directory entirely (you're
   reading tracked files, not git's internal object store, here) and
   skipping anything binary/huge as a safety net. Read each file as text
   (guard the decode -- not everything is UTF-8), run your detection
   heuristics from hint 2 against its content, and for each hit emit a
   finding with `source: "worktree"`, `path` relative to `repo_path` (use
   forward slashes), and `commit: None`.
2. *History pass.* Get the full commit list (`git log --all --pretty=%H`,
   split on newlines). For each commit, list its files (`git ls-tree -r
   --name-only <sha>`) and, for files you have NOT already reported from
   the worktree pass at that same path, pull their content with `git show
   <sha>:<path>` and run the SAME heuristics. When a heuristic hits, emit a
   finding with `source: "history"`, the `commit` sha, and `path`. This is
   also where the dedup from hint 2 matters: if you already have a
   worktree finding for a given path, you generally don't need to also
   walk every historical commit that also happens to contain it -- you're
   hunting for things ONLY visible in history, not re-confirming things
   you already found.

Think about subprocess mechanics: `subprocess.run(["git", "-C",
str(repo_path), <args...>], capture_output=True, text=True)` is enough for
every git command you need here; check `returncode` (or just call
`.check_returncode()`) rather than assuming success.

**Half A precision, concretely.** For the "committed then removed" file
specifically: your history pass should find it (it's a real file in one
commit's tree) and your worktree pass should NOT (it's genuinely absent
from `repo_path` as checked out) -- if your worktree pass somehow "finds"
it too, something is wrong with how you're reading the working tree, not
with the fixture.

**Half B shape.** In `load_secret`: build the env var name as
`f"{name.upper()}_FILE"`, look it up with `os.environ.get(...)` (not `[]`)
so you can raise your OWN clear message rather than a bare `KeyError` when
it's missing, then `Path(...).read_text()` the file it names (letting a
missing/unreadable file's own `OSError` propagate, or catching and
re-raising with more context -- either is "failing loudly"; silently
catching and returning something is not). Strip exactly one trailing
newline (`.removesuffix("\n")` or an `rstrip("\n")` limited to a single
trailing character) rather than stripping all whitespace, so you don't
accidentally eat meaningful leading/trailing spaces from a real secret.

For `service/docker-compose.yml`: replace the `PG_PASSWORD: "..."` line
under `worker`'s `environment:` with `PG_PASSWORD_FILE:
/run/secrets/pg_password`, add a top-level

```yaml
secrets:
  pg_password:
    file: ./secrets/pg_password.txt
```

and give `worker` its own `secrets: [pg_password]` (or the equivalent
list-item form). You don't need `./secrets/pg_password.txt` to actually
exist for the validator (it tests `load_secret` directly against its own
temp file) -- but creating it locally, gitignored, is a reasonable way to
sanity-check the whole picture yourself if you want to.
