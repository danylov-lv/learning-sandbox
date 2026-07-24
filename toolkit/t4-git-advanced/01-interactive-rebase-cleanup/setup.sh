#!/usr/bin/env bash
# Builds (or rebuilds, from scratch) the messy history in
# 01-interactive-rebase-cleanup/work/. Safe to re-run any time you want to
# throw away your progress and start over -- it always deletes work/ first.
#
# Each commit below rewrites price_alert.py/README.md in full (rather than
# patching with sed) so the exact cumulative content at every step is
# visible directly in this script and reproducible byte-for-byte.
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

# --- commit 1: initial commit -------------------------------------------
cat > price_alert.py <<'EOF'
"""Price alert scaffold for the toolkit t4 rebase-cleanup exercise."""

CONFIG = {
    "threshold_pct": 5.0,
}


def load_config():
    return dict(CONFIG)
EOF
cat > README.md <<'EOF'
# price-alert

Scratch project for the git rebase cleanup exercise.
EOF
git add .gitattributes price_alert.py README.md
commit "Initial commit" "2024-03-01T09:00:00+0000"

# --- commit 2: add threshold check (bug: wrong comparison, fixed by commit 5)
cat > price_alert.py <<'EOF'
"""Price alert scaffold for the toolkit t4 rebase-cleanup exercise."""

CONFIG = {
    "threshold_pct": 5.0,
}


def load_config():
    return dict(CONFIG)


def check_threshold(old_price, new_price, threshold_pct):
    if old_price == 0:
        return False
    change_pct = (new_price - old_price) / old_price * 100
    return change_pct > threshold_pct
EOF
git add price_alert.py
commit "add threshold check" "2024-03-01T10:00:00+0000"

# --- commit 3: real content, TYPO in the commit message ------------------
# send_alert is inserted ABOVE check_threshold (not appended at file end) so
# that check_threshold stays the last function in the file -- this keeps
# commit 5's fixup context from spilling into a function that doesn't exist
# yet at that point once autosquash reorders it earlier in the sequence.
cat > price_alert.py <<'EOF'
"""Price alert scaffold for the toolkit t4 rebase-cleanup exercise."""

CONFIG = {
    "threshold_pct": 5.0,
}


def load_config():
    return dict(CONFIG)


def send_alert(product, change_pct):
    return f"ALERT: {product} moved {change_pct:.1f}%"


def check_threshold(old_price, new_price, threshold_pct):
    if old_price == 0:
        return False
    change_pct = (new_price - old_price) / old_price * 100
    return change_pct > threshold_pct
EOF
git add price_alert.py
commit "Add pric alret logic" "2024-03-01T11:00:00+0000"

# --- commit 4: stray debug commit, isolated to its own new file (drop this)
printf 'debug run 1\nthreshold=5.0 old=100 new=104\n' > debug.log
git add debug.log
commit "WIP debug" "2024-03-01T12:00:00+0000"

# --- commit 5: fixup! for commit 2's bug ---------------------------------
cat > price_alert.py <<'EOF'
"""Price alert scaffold for the toolkit t4 rebase-cleanup exercise."""

CONFIG = {
    "threshold_pct": 5.0,
}


def load_config():
    return dict(CONFIG)


def send_alert(product, change_pct):
    return f"ALERT: {product} moved {change_pct:.1f}%"


def check_threshold(old_price, new_price, threshold_pct):
    if old_price == 0:
        return False
    change_pct = (new_price - old_price) / old_price * 100
    return abs(change_pct) >= threshold_pct
EOF
git add price_alert.py
commit "fixup! add threshold check" "2024-03-01T13:00:00+0000"

# --- commit 6: extend send_alert with a channel argument ------------------
cat > price_alert.py <<'EOF'
"""Price alert scaffold for the toolkit t4 rebase-cleanup exercise."""

CONFIG = {
    "threshold_pct": 5.0,
}


def load_config():
    return dict(CONFIG)


def send_alert(product, change_pct, channel="console"):
    message = f"ALERT: {product} moved {change_pct:.1f}%"
    if channel == "email":
        return f"[email] {message}"
    return message


def check_threshold(old_price, new_price, threshold_pct):
    if old_price == 0:
        return False
    change_pct = (new_price - old_price) / old_price * 100
    return abs(change_pct) >= threshold_pct
EOF
git add price_alert.py
commit "add email notification channel" "2024-03-01T14:00:00+0000"

# --- commit 7: fixup! for commit 6's bug (case-sensitive channel check) ---
cat > price_alert.py <<'EOF'
"""Price alert scaffold for the toolkit t4 rebase-cleanup exercise."""

CONFIG = {
    "threshold_pct": 5.0,
}


def load_config():
    return dict(CONFIG)


def send_alert(product, change_pct, channel="console"):
    message = f"ALERT: {product} moved {change_pct:.1f}%"
    if channel.lower() == "email":
        return f"[email] {message}"
    return message


def check_threshold(old_price, new_price, threshold_pct):
    if old_price == 0:
        return False
    change_pct = (new_price - old_price) / old_price * 100
    return abs(change_pct) >= threshold_pct
EOF
git add price_alert.py
commit "fixup! add email notification channel" "2024-03-01T15:00:00+0000"

# --- commit 8: update README ----------------------------------------------
cat > README.md <<'EOF'
# price-alert

Scratch project for the git rebase cleanup exercise.

## Usage

    from price_alert import check_threshold, send_alert

    if check_threshold(old, new, 5.0):
        send_alert("widget", (new - old) / old * 100, channel="email")
EOF
git add README.md
commit "update README" "2024-03-01T16:00:00+0000"

echo "== messy history built in $WORK_DIR =="
git log --oneline
echo
echo "8 commits on main. Clean it up per README.md's target spec, then run:"
echo "  uv run python tests/validate.py"
echo "from the task directory (toolkit/t4-git-advanced/01-interactive-rebase-cleanup)."
