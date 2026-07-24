#!/usr/bin/env bash
# Builds (or rebuilds, from scratch) a 14-commit linear history in
# 02-bisect-find-regression/work/, where one hidden commit introduces a
# pricing regression. Safe to re-run any time you want to throw away your
# progress and start over -- it always deletes work/ first.
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

write_is_bad() {
  cat > is_bad.sh <<'EOF'
#!/usr/bin/env bash
# Exit 0 if pricing.sh's price_after_discount is correct, non-zero if not.
# Used as the "test script" for `git bisect run`.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/pricing.sh"
result="$(price_after_discount 200 10)"
[ "$result" = "180" ]
EOF
}

# --- commit 1: initial pricing script + is_bad.sh -------------------------
cat > pricing.sh <<'EOF'
#!/usr/bin/env bash
# price_after_discount PRICE DISCOUNT_PCT -> integer price after discount.
price_after_discount() {
  local price="$1"
  local discount="$2"
  echo $(( price - price * discount / 100 ))
}
EOF
write_is_bad
cat > README.md <<'EOF'
# pricing-cli

Scratch project for the git bisect exercise.
EOF
git add .gitattributes pricing.sh is_bad.sh README.md
commit "init pricing script" "2024-04-01T09:00:00+0000"

# --- commit 2: unrelated doc change ---------------------------------------
cat >> README.md <<'EOF'

## Usage

    source pricing.sh
    price_after_discount 200 10
EOF
git add README.md
commit "add README usage notes" "2024-04-01T10:00:00+0000"

# --- commit 3: unrelated new helper (tax_amount), does not touch discount -
cat >> pricing.sh <<'EOF'

# tax_amount PRICE TAX_PCT -> integer tax amount.
tax_amount() {
  local price="$1"
  local tax="$2"
  echo $(( price * tax / 100 ))
}
EOF
git add pricing.sh
commit "add tax_amount helper" "2024-04-01T11:00:00+0000"

# --- commit 4: cosmetic refactor of variable names, math unchanged --------
cat > pricing.sh <<'EOF'
#!/usr/bin/env bash
# price_after_discount PRICE DISCOUNT_PCT -> integer price after discount.
price_after_discount() {
  local amount="$1"
  local pct="$2"
  echo $(( amount - amount * pct / 100 ))
}

# tax_amount PRICE TAX_PCT -> integer tax amount.
tax_amount() {
  local price="$1"
  local tax="$2"
  echo $(( price * tax / 100 ))
}
EOF
git add pricing.sh
commit "refactor variable names in pricing.sh" "2024-04-01T12:00:00+0000"

# --- commit 5: comment header, no logic change -----------------------------
cat > pricing.sh <<'EOF'
#!/usr/bin/env bash
# pricing.sh -- integer pricing helpers for the bisect exercise scratch repo.

# price_after_discount PRICE DISCOUNT_PCT -> integer price after discount.
price_after_discount() {
  local amount="$1"
  local pct="$2"
  echo $(( amount - amount * pct / 100 ))
}

# tax_amount PRICE TAX_PCT -> integer tax amount.
tax_amount() {
  local price="$1"
  local tax="$2"
  echo $(( price * tax / 100 ))
}
EOF
git add pricing.sh
commit "add comment header to pricing.sh" "2024-04-01T13:00:00+0000"

# --- commit 6: unrelated README note ---------------------------------------
cat >> README.md <<'EOF'

Amounts are integer cents; there is no rounding step.
EOF
git add README.md
commit "add rounding note to README" "2024-04-01T14:00:00+0000"

# --- commit 7: unrelated new helper (currency label) ------------------------
cat >> pricing.sh <<'EOF'

# format_currency AMOUNT -> AMOUNT prefixed with a currency symbol.
format_currency() {
  local amount="$1"
  echo "\$${amount}"
}
EOF
git add pricing.sh
commit "add currency helper function" "2024-04-01T15:00:00+0000"

# --- commit 8: unrelated tweak to tax_amount (does not touch discount) -----
cat > pricing.sh <<'EOF'
#!/usr/bin/env bash
# pricing.sh -- integer pricing helpers for the bisect exercise scratch repo.

# price_after_discount PRICE DISCOUNT_PCT -> integer price after discount.
price_after_discount() {
  local amount="$1"
  local pct="$2"
  echo $(( amount - amount * pct / 100 ))
}

# tax_amount PRICE TAX_PCT -> integer tax amount, using the standard rate.
STANDARD_TAX_PCT=8
tax_amount() {
  local price="$1"
  local tax="${2:-$STANDARD_TAX_PCT}"
  echo $(( price * tax / 100 ))
}

# format_currency AMOUNT -> AMOUNT prefixed with a currency symbol.
format_currency() {
  local amount="$1"
  echo "\$${amount}"
}
EOF
git add pricing.sh
commit "tweak tax_amount default rate" "2024-04-01T16:00:00+0000"

# --- commit 9: THE REGRESSION -----------------------------------------------
# "Simplifies" the discount formula by dropping the percentage scaling --
# price_after_discount(200, 10) now returns 190 instead of 180.
cat > pricing.sh <<'EOF'
#!/usr/bin/env bash
# pricing.sh -- integer pricing helpers for the bisect exercise scratch repo.

# price_after_discount PRICE DISCOUNT_PCT -> integer price after discount.
price_after_discount() {
  local amount="$1"
  local pct="$2"
  echo $(( amount - pct ))
}

# tax_amount PRICE TAX_PCT -> integer tax amount, using the standard rate.
STANDARD_TAX_PCT=8
tax_amount() {
  local price="$1"
  local tax="${2:-$STANDARD_TAX_PCT}"
  echo $(( price * tax / 100 ))
}

# format_currency AMOUNT -> AMOUNT prefixed with a currency symbol.
format_currency() {
  local amount="$1"
  echo "\$${amount}"
}
EOF
git add pricing.sh
commit "simplify discount formula" "2024-04-01T17:00:00+0000"

# --- commit 10: unrelated addition, bug persists ----------------------------
cat >> pricing.sh <<'EOF'

# log_price LABEL AMOUNT -> prints a labeled amount line.
log_price() {
  local label="$1"
  local amount="$2"
  echo "${label}: ${amount}"
}
EOF
git add pricing.sh
commit "add logging function" "2024-04-01T18:00:00+0000"

# --- commit 11: unrelated README changelog entry ----------------------------
cat >> README.md <<'EOF'

## Changelog

- Added tax and currency helpers.
EOF
git add README.md
commit "update README changelog" "2024-04-01T19:00:00+0000"

# --- commit 12: unrelated validation helper, bug persists -------------------
cat >> pricing.sh <<'EOF'

# valid_discount_pct PCT -> 0 if 0<=PCT<=100, 1 otherwise.
valid_discount_pct() {
  local pct="$1"
  [ "$pct" -ge 0 ] && [ "$pct" -le 100 ]
}
EOF
git add pricing.sh
commit "add validate discount range check" "2024-04-01T20:00:00+0000"

# --- commit 13: whitespace-only cleanup, bug persists ------------------------
cat > pricing.sh <<'EOF'
#!/usr/bin/env bash
# pricing.sh -- integer pricing helpers for the bisect exercise scratch repo.


# price_after_discount PRICE DISCOUNT_PCT -> integer price after discount.
price_after_discount() {
  local amount="$1"
  local pct="$2"
  echo $(( amount - pct ))
}

# tax_amount PRICE TAX_PCT -> integer tax amount, using the standard rate.
STANDARD_TAX_PCT=8
tax_amount() {
  local price="$1"
  local tax="${2:-$STANDARD_TAX_PCT}"
  echo $(( price * tax / 100 ))
}

# format_currency AMOUNT -> AMOUNT prefixed with a currency symbol.
format_currency() {
  local amount="$1"
  echo "\$${amount}"
}

# log_price LABEL AMOUNT -> prints a labeled amount line.
log_price() {
  local label="$1"
  local amount="$2"
  echo "${label}: ${amount}"
}

# valid_discount_pct PCT -> 0 if 0<=PCT<=100, 1 otherwise.
valid_discount_pct() {
  local pct="$1"
  [ "$pct" -ge 0 ] && [ "$pct" -le 100 ]
}
EOF
git add pricing.sh
commit "clean up whitespace" "2024-04-01T21:00:00+0000"

# --- commit 14: unrelated final comment polish, bug persists -----------------
cat >> README.md <<'EOF'

---
Generated for toolkit/t4-git-advanced, task 02.
EOF
git add README.md
commit "final polish comment" "2024-04-01T22:00:00+0000"

echo "== 14-commit history built in $WORK_DIR =="
git log --oneline
echo
echo "One of these commits introduced a pricing regression. Use 'git bisect'"
echo "with is_bad.sh to find the FIRST bad commit, then write its full SHA"
echo "into FIRST_BAD_SHA.txt (in this task directory, not inside work/)."
echo "Then run: uv run python tests/validate.py"
