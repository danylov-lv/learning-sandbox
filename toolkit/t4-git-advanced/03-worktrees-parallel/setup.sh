#!/usr/bin/env bash
# Builds (or rebuilds, from scratch) a one-commit repo in
# 03-worktrees-parallel/work/. Safe to re-run any time you want to throw
# away your progress and start over -- it always deletes work/ first,
# which also removes any worktrees you created under work/.worktrees/.
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

cat > toolkit-notes.md <<'EOF'
# toolkit-notes

Shared notes file on main. Two features are about to be worked on in
parallel, in two separate worktrees -- this file is not touched by
either of them.
EOF
git add .gitattributes toolkit-notes.md
commit "Initial commit" "2024-05-01T09:00:00+0000"

echo "== repo built in $WORK_DIR =="
git log --oneline
echo
echo "main has 1 commit. Create two worktrees on two feature branches per"
echo "README.md, make the specified commit on each, then run:"
echo "  uv run python tests/validate.py"
echo "from the task directory (toolkit/t4-git-advanced/03-worktrees-parallel)."
