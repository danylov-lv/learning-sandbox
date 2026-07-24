# Live verification notes (toolkit/t4-git-advanced)

Spoilers. Read after finishing the module, not before.

## What was verified, per task

All five validators were run from their task directory against the
stock (freshly `setup.sh`'d, unsolved) state, confirmed to print exactly
one `NOT PASSED: <reason>` line and exit 1 with zero traceback lines,
then a throwaway correct solve was performed directly against the
gitignored `work/` scratch repo (or, for task 05, a throwaway fully
filled `POLICY.md`), confirmed to print `PASSED`, then the task was
reset (`setup.sh` rerun for 01-04, the filled `POLICY.md` reverted
byte-identical via `diff` for 05) so nothing solved was left behind.

- **01-interactive-rebase-cleanup**: stock 8-commit history fails with
  `main has 8 commit(s), expected 5`. Throwaway solve used
  `git rebase -i --autosquash --root main` with `GIT_SEQUENCE_EDITOR`
  (script rewriting the `WIP debug` line to `drop` and the
  `Add pric alret logic` line to `reword`) and `GIT_EDITOR` (script
  rewriting the reworded message) -- reached exactly the target 5-commit
  shape with **zero merge conflicts** after the file-layout fix
  documented in `design.md` (first attempt, before that fix, hit a real
  `CONFLICT (content)` on the threshold fixup -- see design.md for why,
  and don't reintroduce that layout if this task is ever extended).
  Validator printed `PASSED: main: 5 linear commits, messages and tree
  match target`. Reset via `setup.sh` confirmed back to the 8-commit
  stock-fail state.
- **02-bisect-find-regression**: stock fails with `FIRST_BAD_SHA.txt
  still has the placeholder`. Throwaway solve used a real
  `git bisect start` / `git bisect bad main` / `git bisect good <first
  sha>` / `git bisect run bash is_bad.sh` -- bisect itself converged
  live to `f7b636c0...`, matching the validator's own independent
  history walk exactly. Validator printed `PASSED: first bad commit
  correctly identified: f7b636c0ce4fd0e91c0f5e9c3ea36d742715a5f0` after
  writing that SHA into `FIRST_BAD_SHA.txt` and running `git bisect
  reset`. **Confirmed the answer file was reset back to the placeholder
  `PASTE_FULL_SHA_HERE` after verification** -- no SHA is left committed
  in the shipped file.
- **03-worktrees-parallel**: stock fails with `branch 'feature/alpha'
  not found in work/`. Throwaway solve used `git worktree add
  .worktrees/alpha -b feature/alpha` / `.worktrees/beta -b
  feature/beta`, committed the two specified files/messages inside each
  worktree. Validator printed `PASSED: both feature branches correct,
  main untouched, both worktrees still attached`. Reset via `setup.sh`
  (which deletes all of `work/`, including the linked worktrees under
  it) confirmed back to stock-fail.
- **04-reflog-rescue**: stock fails with `branch
  'feature/valuable-work' does not exist`. Throwaway solve read
  `git reflog show HEAD`, found the lost tip SHA at the `commit: Switch
  retry design to exponential backoff` entry, and ran `git branch
  feature/valuable-work <that sha>`. Validator printed `PASSED:
  'feature/valuable-work' recovered at the original commit
  3ce744f4e10a99e00b035bc10d68739ede711090; main untouched`. Reset via
  `setup.sh` confirmed back to stock-fail (branch deleted again).
- **05-history-design-writeup**: stock (template) `POLICY.md` fails on
  `check_sections` length before reaching placeholder/keyword checks
  (several sections' instructional placeholder text sits just under
  their `min_chars` threshold) -- still a single clean `NOT PASSED`
  line. A throwaway fully filled `POLICY.md` (concrete rules in every
  section, all 6 `### Qn` answered as direct applications of those
  sections) passed cleanly:
  `PASSED: POLICY.md structure, grounding vocabulary, and all 6
  hostile-review answers OK`. The file was then overwritten back to the
  exact shipped template (verified with `diff` against a pre-edit copy
  -- byte-identical) and the stock-fail re-confirmed afterward.

## Determinism, confirmed live

For each of tasks 01-04, `setup.sh` was run twice in a row and
`git -C work rev-parse main` compared -- identical both times in every
case (see the exact SHAs in `.authoring/design.md`). This is what makes
hardcoding expected SHAs in tasks 03/04's validators (and the
stock/target tree content in task 01's) safe: the same learner, on the
same machine, gets the same starting SHAs on every `setup.sh` rerun, and
so does anyone else regenerating this module from the committed
`setup.sh` scripts on a different machine (Windows Git, in this case --
see the git-on-Windows gotchas below for what determinism actually
required).

## git-on-Windows gotchas found and worked around

1. **`core.autocrlf` / line-ending normalization would have broken SHA
   determinism.** Every `setup.sh` explicitly sets
   `git config core.autocrlf false` and `core.eol lf`, and commits a
   `.gitattributes` with `* -text` as the very first tracked file, before
   any other content is written. Without this, a learner (or CI runner)
   with a global `core.autocrlf=true` (common default on Windows) would
   get CRLF-normalized blobs on checkout/add, producing different blob
   SHAs than the ones hardcoded in the validators, even though this
   module was authored and verified entirely on Windows Git
   (`git version 2.48.1.windows.1`) in Git Bash.
2. **Heredoc content generation, not sed/perl patching.** Early drafts of
   task 01's `setup.sh` used inline `python3 -c` / `perl -pi` patches
   with a `||`-chained fallback to rewrite `price_alert.py` between
   commits. This added a real dependency-detection branch for no benefit,
   since every commit's full content is already known at authoring time
   -- rewritten to `cat > file <<'EOF' ... EOF` full-file overwrites at
   every commit step instead. Simpler, has zero interpreter dependency,
   and makes the exact diff between any two commits directly readable in
   `setup.sh` itself.
3. **`git bisect` and `git worktree` both worked exactly as documented in
   Git Bash on Windows** -- no path-separator or shell-quoting surprises
   in either task, including worktree paths nested under `work/` (a
   relative `.worktrees/alpha` path, resolved from inside `work/`).
4. **`is_bad.sh` (task 02) invoked as `bash is_bad.sh`, never
   `./is_bad.sh`**, both in the README's instructions and the validator's
   own subprocess calls -- sidesteps the executable-bit question
   entirely, which is meaningless on a Windows filesystem/Git Bash
   combination anyway.

## No reference solutions committed

Confirmed via `git status --porcelain -uall toolkit/t4-git-advanced`
after every reset: only the intended authored files (README, setup.sh,
tests/validate.py, hints, NOTES.md, the module root files, `.authoring/`)
show as untracked/new -- no `work/` content, no `.venv/`, no
`__pycache__/` leaks into that listing (spot-checked with
`git check-ignore -v` against each task's `work/` directory and the
module's `.venv/`, both correctly matched by this module's own
`.gitignore` on top of the repo-root one). `FIRST_BAD_SHA.txt` ships
with the placeholder, not a solved value. `POLICY.md` ships as the
unfilled template, confirmed byte-identical via `diff` to a pre-edit
backup after the throwaway fill/revert cycle.
