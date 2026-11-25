---
name: add-new-module
description: Design and add a new numbered module or toolkit track module to learning-sandbox. Use when the learner wants a new module from a topic, including topics from the course roadmap.
---

# Add a learning-sandbox module

## Design the module

Establish what the learner already knows, what they should be able to do by the end, and how much time they want to spend. Use confirmed context and ask only for missing details that change the design. A small module has 4–6 single-evening exercises, a standard module has 8–12 exercises plus a capstone, and a deep module has 12 or more exercises and a multi-evening capstone.

Read the global sections of `docs/authoring/SPEC.md` and the relevant rules in `docs/authoring/CONVENTIONS.md`. Check module headings and `docs/authoring/GENERATION_STATE.md` for overlap. Read related module specs where they affect prerequisites or content.

Draft the spec around the intended learning outcomes. Use representative engineering problems or focused exercises that make a concept concrete. State what prior skills, earlier work, and services the module requires. Reuse suitable datasets, design for the documented local environment, and explain the limits of any local approximation. Check version-sensitive requirements against official documentation.

For each exercise, state its learning outcome, what the learner will submit, the observable behavior that earns a pass, and a plausible mistake the check will catch. When the method itself is a learning outcome, identify evidence that demonstrates its use. Specify independent expected results or observations and explain how checks involving failures, concurrency, or performance will be reproduced.

## Validate the learning path

Walk through the draft in the learner's order, from the stated prerequisites to the final outcome. For each exercise, check that the brief and provided materials let the learner start, the work they do trains the intended skill, and the check rewards the behavior the exercise promises to teach. Provide scaffolding for incidental setup when it would crowd out the intended practice.

Check that the sequence gives the learner a chance to practice each stated outcome and that each exercise introduces a capability, applies it under a meaningful new constraint, or combines earlier skills. A capstone should draw on skills the learner has had a chance to practice. Use these same criteria to review the built module before marking it generated.

## Agree on scope and placement

Propose a position based on the module's prerequisites and what it prepares the learner for. A numbered module's ID matches its position in the agreed sequence of numbered modules. If insertion or reordering shifts existing modules, include an old-to-new ID mapping for every affected module. Use the appropriate existing prefix for toolkit modules. Present the spec and wait for explicit approval before editing repository files or generating exercises.

## Build and verify

Apply any approved renumbering as a separate repository change. Move affected modules as units and carry their learner work and completion records with them. Update affected roadmap entries, progress lists, specifications, generation state, registry, CI selectors, setup commands, links, and prerequisites. Verify that changed IDs resolve to the intended modules and that service configuration and port documentation agree.

Register the new module in `README.md`, `docs/authoring/SPEC.md`, `docs/authoring/GENERATION_STATE.md`, `docs/PROGRESS.md`, and `ci-meta/registry.py`. Keep its generation status pending while building its exercise briefs, scaffolds, deterministic data, hints, and validators. Leave the exercise solutions to the learner.

Repeat the learning-path review against the actual briefs, scaffolds, fixtures, and validator contracts. Fix mismatches between what the module is meant to teach and what the exercises require or reward.

Verify the documented environment. Exercise each new validator on the intended pass and a representative failure with disposable inputs or implementations. Keep temporary solutions outside the repository. Run `python ci-meta/run_module_ci.py <module-id>`, `python ci-meta/repo_guards.py`, and `python ci-meta/tests/validate.py`. Record the results of the learning-path review, technical checks, and any limits before marking the module generated.
