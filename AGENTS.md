# Working in learning-sandbox

## Purpose and collaboration

This is a project-based engineering course. The learner writes exercise solutions; Codex supports reviews, explanations, validators, scaffolding, and course maintenance. During reviews, report concrete findings and guide the learner without rewriting their solution. Keep ready-made exercise solutions out of the repository.

Give exercise hints only when the learner explicitly asks for them.

## Read only what the task needs

- Read `docs/authoring/CONVENTIONS.md` before editing course materials for task structure, verification rules, and track-specific exceptions.
- When asked to resume learning, use the course order in README.md and read only the relevant section of `docs/PROGRESS.md` and the candidate task's README. If an unchecked task has a learner submission, consult its documented completion criteria and verify it when the required environment is available. Identify the next exercise and report any discrepancy or verification blocker. Preserve completion checkboxes unless the user asks to update them.
- For a new module, use `$add-new-module` (`.agents/skills/add-new-module/SKILL.md`).
- For changes to an existing module, read the global sections of `docs/authoring/SPEC.md`, its relevant `## MODULE:` section, and the matching entry in `docs/authoring/GENERATION_STATE.md`. Use `$modify-existing-module` (`.agents/skills/modify-existing-module/SKILL.md`) when changing the module's learning outcomes, prerequisites, scope, or exercise sequence.
- For requests to plan a module's lecture course, write or revise its teaching materials, or resume lecture authoring, use `$author-module-lectures`. Read and follow `.agents/skills/author-module-lectures/SKILL.md` when the learner names the skill or describes the work in plain language.
- For an exercise review, read its README, submitted work, and relevant tests. Treat .authoring directories as spoilers; use them only when necessary for authoring or a validator audit, and keep their ground truth out of learner feedback.

Start with top-level listings and targeted searches. Avoid recursively reading the course, environments, generated data, or all of SPEC.md. Keep unrelated learner edits intact.

## Validation

Use the affected module's documented commands and local dependencies. Python modules use uv; Rust and TypeScript tracks have their own toolchains. Ordinary task validators can fail because an exercise is unsolved. Report that state separately from a broken validator.

For authoring changes, run `python ci-meta/run_module_ci.py <module-id>`. For changes to repository structure or generation state, run `python ci-meta/repo_guards.py` and `python ci-meta/tests/validate.py`. These check course infrastructure, not whether the learner has solved the exercises. State exactly what was verified and any live integration left untested.

Keep task configurations isolated; installing a learner's agents, hooks, or MCP setup into the active repository requires an explicit request.

## Documentation

Maintain one current description of each rule or contract. Replace obsolete guidance rather than appending migration history or session narratives. Preserve grading ground truth and necessary fixture constraints. Verify current official documentation before changing Codex-specific mechanisms.
