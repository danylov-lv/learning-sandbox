# Authoring notes -- 21-helm-vs-kustomize-writeup

Unlike task 06 (which grades against a GIVEN fixture chart with planted,
objectively-identifiable smells), task 21 is a reasoned opinion/design
comparison with no single correct verdict -- so, per the task spec, there
is no answer key here and none should ever exist: not in `COMPARISON.md`,
not in a hint, not in this file. This file only records the doc-gate
wiring so a future author can see why the thresholds are what they are.

## Files

- `README.md` -- backstory (arc 2 hand-written chart + arc 5 Argo CD
  exposure), what's required, completion criteria, topics to read up on.
- `questions.md` -- Q1-Q5 hostile-review questions (8-microservices
  layout, checksum-annotation mechanism per tool, Argo CD app-of-apps
  composition, one concrete win each way, deliberate combined use).
- `COMPARISON.md` -- learner deliverable template. Required `## `
  sections: "Mental models", "Where Helm wins", "Where Kustomize wins",
  "Decision", each with a `[fill in: ...]` placeholder describing what's
  expected. Plus a `## Hostile review` heading (not itself in the
  enforced section list -- mirrors task 06's pattern where `check_answers`
  scans `### Qn` subsections across the whole document rather than a
  single named section) containing `### Q1` .. `### Q5`, each with the
  question restated (for the learner's convenience while editing) and a
  `[fill in]` marker.
- `tests/validate.py` -- `@common.guarded` entry point, no `require_cluster()`,
  no kubectl/kind calls anywhere.
- `hints/hint-1..3.md` -- direction only (mental-models-first ordering,
  how to avoid restating instead of tracing a mechanism per question,
  pointers to which topics from `README.md`'s reading list resolve a thin
  answer). No model answers.
- `NOTES.md` -- `[fill in]` template, ungraded.

## Doc-gate parameters (`tests/validate.py`)

- `check_sections(COMPARISON.md, REQUIRED_SECTIONS, MIN_CHARS)` --
  `REQUIRED_SECTIONS = ["Mental models", "Where Helm wins", "Where
  Kustomize wins", "Decision"]`. `MIN_CHARS`: Mental models 500, Where
  Helm wins 400, Where Kustomize wins 400, Decision 400, `_default` 300.
  "Hostile review" deliberately excluded from this list (matches task 06):
  its `### Qn` subsections are checked separately by `check_answers`,
  which parses `###` headings across the whole document regardless of
  which `##` section they sit under.
- Explicit `"[fill in"` substring scan across the full file after
  `check_sections` passes, same belt-and-suspenders pattern as task 06.
- `check_keywords(full_text, GROUNDING_KEYWORDS, MIN_GROUNDING_HITS=8,
  ...)` -- vocabulary list: `values.yaml`, `overlay`, `patch`,
  `kustomization`, `base`, `subchart`, `dependencies`, `hook`, `checksum`,
  `argo cd`, `app-of-apps`, `strategic merge`, `json 6902`,
  `secretgenerator`, `configmapgenerator`, `component`, `template`,
  `chart.yaml` (18 terms, need >=8 distinct hits). Chosen so a genuine
  writeup clears it comfortably while a vocabulary-free opinion piece
  ("Helm is more flexible, Kustomize is simpler") does not.
- `check_answers(COMPARISON.md, [Q1..Q5], min_answered=5, min_chars=250,
  questions_path=questions.md, min_original_chars=150)` -- all five
  required (mirrors task 06 requiring all of its six); `min_chars=250` and
  `min_original_chars=150` set lower than task 06's (300/300) because this
  task's questions are individually shorter and more scenario-specific
  than task 06's, so a genuine original answer naturally runs a bit
  shorter per question while still clearing the anti-copy bar comfortably.

## Verification performed (live, this session)

1. Stock (unfilled) `COMPARISON.md` -> `uv run python tests/validate.py`
   -> single `NOT PASSED: section(s) too short: 'Where Helm wins'
   (334/400 chars), 'Decision' (316/400 chars)` line, exit 1, no
   traceback. (The unfilled placeholders are short enough that
   `check_sections`'s length gate fires before the placeholder-marker
   gate would -- still a clean single-line rejection either way.)
2. Anti-copy proof (isolated, via a throwaway scratch doc outside the
   task dir, never committed): pasted `questions.md`'s Q1 text verbatim
   as the `### Q1` answer body and called `common.check_answers` directly
   with the same parameters as the validator -> rejected with `Q1
   (mostly restates the question: 0/150 characters of your own)`.
3. Genuine-pass proof: temporarily replaced `COMPARISON.md` with a fully
   and substantively filled version (all 4 sections + 5 Q answers,
   original reasoning, no copied question text) and ran
   `uv run python tests/validate.py` -> `PASSED: COMPARISON.md
   structurally complete (5 required sections); grounding vocabulary
   present; all 5 hostile-review questions answered`, exit 0.
4. Reverted `COMPARISON.md` to the stock template immediately after;
   confirmed via `sha256sum` that the reverted file is byte-identical to
   the original stock file (same hash before and after the throwaway
   fill/revert cycle), and re-ran the validator to confirm it fails
   cleanly again on the restored stub. No filled/model answer was left on
   disk anywhere (not in `COMPARISON.md`, not in hints, not in this file).
5. Confirmed `tests/validate.py` never imports or calls `require_cluster`,
   `kubectl`, or `kind` -- grepped the file; the only textual matches are
   in the module's own docstring stating that no cluster is used.
