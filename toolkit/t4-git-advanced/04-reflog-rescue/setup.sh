#!/usr/bin/env bash
# Builds (or rebuilds, from scratch) a repo in 04-reflog-rescue/work/ that
# ends with a branch deleted out from under valuable, unmerged work. Safe
# to re-run any time you want to throw away your progress and start over
# -- it always deletes work/ first and rebuilds the same disaster from
# scratch (the SHAs are deterministic thanks to fixed author/committer
# dates, so they are the same every time this script runs).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$SCRIPT_DIR/work"

rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

git -c init.defaultBranch=main init -q
git config user.name "Scratch Dev"
git config user.email "scratch-dev@example.invalid"
git config core.autocrlf false
git config core.eol lf
printf '* -text\n' > .gitattributes

commit() {
  # commit <message> <iso-date>
  GIT_AUTHOR_NAME="Scratch Dev" GIT_AUTHOR_EMAIL="scratch-dev@example.invalid" \
  GIT_COMMITTER_NAME="Scratch Dev" GIT_COMMITTER_EMAIL="scratch-dev@example.invalid" \
  GIT_AUTHOR_DATE="$2" GIT_COMMITTER_DATE="$2" \
  git commit -q -m "$1"
}

# --- commit 1: initial commit on main --------------------------------------
cat > README.md <<'EOF'
# payments-scratch

Scratch project for the git reflog rescue exercise.
EOF
cat > notes.md <<'EOF'
# notes

(nothing yet)
EOF
git add .gitattributes README.md notes.md
commit "Initial commit" "2024-06-01T09:00:00+0000"

# --- branch off main: the valuable, soon-to-be-deleted work ----------------
git checkout -q -b feature/valuable-work

cat > payment-retry.md <<'EOF'
# Payment retry design

First pass: retry a failed payment capture up to 3 times with a fixed
1-second delay between attempts.
EOF
git add payment-retry.md
commit "Draft payment retry design" "2024-06-01T10:00:00+0000"

cat > payment-retry.md <<'EOF'
# Payment retry design

First pass: retry a failed payment capture up to 3 times with a fixed
1-second delay between attempts.

Revised: use exponential backoff (1s, 2s, 4s) instead of a fixed delay,
and stop retrying immediately on a card-declined response -- that one
is never going to succeed on retry, unlike a network timeout.
EOF
git add payment-retry.md
commit "Switch retry design to exponential backoff" "2024-06-01T11:00:00+0000"

# --- back to main, which keeps moving after the branch is lost -------------
git checkout -q main

cat >> notes.md <<'EOF'

- 2024-06-01: reminder to follow up on payment retry design with the
  payments team once it's ready for review.
EOF
git add notes.md
commit "update notes" "2024-06-01T12:00:00+0000"

# --- the disaster: force-delete the unmerged branch -------------------------
git branch -D feature/valuable-work >/dev/null

echo "== repo built in $WORK_DIR =="
echo "main:"
git log --oneline main
echo
echo "feature/valuable-work no longer exists as a branch -- it was deleted"
echo "with 'git branch -D' while still unmerged. Its commits are dangling"
echo "but not gone. Recover it, then run:"
echo "  uv run python tests/validate.py"
echo "from the task directory (toolkit/t4-git-advanced/04-reflog-rescue)."
