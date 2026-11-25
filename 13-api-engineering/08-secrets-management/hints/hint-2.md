# Hint 2 -- more specific

**Half A, the history pass.** `git log` by default only shows history
reachable from the branch you're on. That's usually fine, but a scanner
that wants to be sure it isn't missing anything should be explicit:
`git log --all` walks every commit reachable from *any* ref (all branches,
not just the current one). To enumerate commits in a script-friendly way,
`git log --all --pretty=%H` gives you one full sha per line -- that's your
list of "every commit that exists in this repo." For each sha, `git
ls-tree -r --name-only <sha>` lists every file path in that commit's
snapshot, and `git show <sha>:<path>` prints one file's content AT that
commit, without touching the working directory or your current checkout at
all. Put those three together and you can inspect every file, at every
point in history, the same way you'd inspect the working tree -- just
against a different snapshot each time.

Two efficiency/precision notes worth thinking about before you code it:
(a) the same secret often exists unchanged across MANY commits (added once,
never touched again) -- if you naively report every commit that contains
it, you'll flood your own findings list and blow through the "don't just
report everything" precision check; think about what actually needs a
`source: "history"` finding versus what's already covered by a `source:
"worktree"` finding for the same file. (b) a commit that *removed* a file
does not itself contain that file in its tree -- the commit where the file
is present is an earlier one.

**Half A, precision.** A few concrete signal categories worth combining
(no single one is sufficient alone): filenames/paths that are conventionally
sensitive (`.env`, `*.pem`, `id_rsa`-shaped names); key names in
config-like files that scream secret (`PASSWORD`, `SECRET`, `TOKEN`, `KEY`,
`DSN` as a substring of a variable name); recognizable credential SHAPES
(a PEM header/footer pair, a connection-string URL with a `user:password@`
segment, a cloud-provider access-key-id prefix); and, as a tie-breaker,
whether the value looks like it was clearly written as a stand-in on
purpose (empty, a documented example string, or otherwise obviously not
meant to work).

**Half B.** The compose `secrets:` shape has two parts that both need to
exist and agree: a TOP-LEVEL `secrets:` block declaring where the material
lives (`file: <path>` -- the file itself doesn't need real content for this
task, since nothing here actually runs `docker compose up`), and, under the
SERVICE that needs it, a `secrets:` list naming which top-level secret to
mount. On the loader side: think about what "fail loudly" actually means
as a Python contract -- not printing a warning and returning `None` or `""`
(a caller that doesn't check the return value would sail right past that),
but *raising*, so a missing secret stops the program instead of quietly
running with a broken connection.
