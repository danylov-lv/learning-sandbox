"""s12.t08 (half A) -- find the leaked secret.

Implement `scan_repo` to scan a git repository for leaked secrets, in BOTH
the current working tree AND the full commit history. A secret can be
committed and later "removed" in a later commit -- `git log -p` / `git show`
still reveals it even though the file is gone from the checked-out tree; a
plain recursive grep over the working directory does not.

Return a list of findings. Each finding is a dict with exactly these keys:

    {
        "type":   str,   # your own short label for what kind of secret this
                          # looks like, e.g. "hardcoded_dsn", "private_key",
                          # "cloud_access_key" -- free text, not graded
                          # verbatim, but should be genuinely descriptive.
        "path":   str,    # repo-relative file path where the secret lives,
                          # e.g. "src/config.py" or ".env" -- forward
                          # slashes, no leading "./".
        "value":  str,    # the leaked secret text you found (the actual
                          # sensitive substring/line -- not a redacted
                          # placeholder).
        "source": str,    # "worktree" if you found it by reading the
                          # CURRENT checked-out files, or "history" if you
                          # only found it by scanning past commits (i.e. it
                          # is NOT present in the current working tree).
        "commit": str | None,  # the commit sha you found it in. REQUIRED
                          # (non-empty) when source == "history". None (or
                          # simply omitted) when source == "worktree".
    }

`repo_path` is the filesystem path to a REAL git repository (it has a
`.git/` directory) -- use the `git` CLI via `subprocess` (e.g. `git -C
<repo_path> log --all --pretty=%H` to list every commit reachable from any
ref, `git -C <repo_path> ls-tree -r --name-only <sha>` to list a commit's
files, `git -C <repo_path> show <sha>:<path>` to read a file's content AT
that commit without checking anything out) or a Python git library if you
prefer. Nothing in the harness does this for you.

Precision matters as much as recall. The fixture also plants realistic
DECOYS -- an AWS docs example key, an empty `.env.example` template, a
public key file, a changelog entry that happens to contain a hex string --
that must NOT show up in your findings. Don't just regex "anything
base64/hex-looking and long": think about what actually distinguishes a
secret from a placeholder, a public value, or a random-looking-but-harmless
hash, and design your detection so it tells them apart.
"""


def scan_repo(repo_path) -> list[dict]:
    """Scan the git repository at `repo_path` for leaked secrets, covering
    both the working tree and the full commit history. See the module
    docstring above for the exact required return schema."""
    raise NotImplementedError
