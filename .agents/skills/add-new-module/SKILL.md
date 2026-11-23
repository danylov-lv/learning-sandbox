---
name: add-new-module
description: Design and add a new numbered module or toolkit track module to learning-sandbox. Use when the learner wants a new module from a topic, including topics from the course roadmap.
---

# Add a learning-sandbox module

## Draft the module spec

1. Establish the topic, the learner's experience with it, their goal, and the desired size. Use details already confirmed in the conversation and ask only for missing details that would change the design. Size options are small (4-6 single-evening tasks), standard (8-12 tasks plus a capstone), and deep (12+ tasks and a multi-evening capstone).
2. Read the global sections of `docs/authoring/SPEC.md` above `# Module specs` and the applicable rules in `docs/authoring/CONVENTIONS.md`. Check `## MODULE:` headings and the relevant entries in `docs/authoring/GENERATION_STATE.md` to identify overlap. Read existing module sections only where they affect the design or prerequisites.
3. Draft a spec in the style of the existing module entries. Include a realistic backstory, a progression from foundations to applied work, verification per task type, dependencies on earlier work or services, and a capstone when warranted. Reuse seeded datasets and build on skills taught by existing modules. Fit the documented local environment. When a production topology is too large, specify a local approximation and a written exercise on where it differs. Verify current official documentation before relying on fast-moving tools or features.
4. Present the draft and wait for explicit approval before editing repository files or generating tasks.

## Build the approved module

1. Assign the next free number or the appropriate track prefix. Add the approved spec to `docs/authoring/SPEC.md` under a `## MODULE:` heading. Add a pending entry in `docs/authoring/GENERATION_STATE.md`, the route in `README.md`, unchecked exercises in `docs/PROGRESS.md`, and the module registration in `ci-meta/registry.py`.
2. Build the scaffolds, deterministic data, hints, and validators under the new module. Preserve existing modules and learner work. The learner supplies exercise solutions.
3. Verify the module's documented environment and required checks. Run `python ci-meta/run_module_ci.py <module-id>`. Record actual verification results and limits before marking the module generated. Run `python ci-meta/repo_guards.py` and `python ci-meta/tests/validate.py` with the final inventory. Report any remaining authoring work or untested integrations.
