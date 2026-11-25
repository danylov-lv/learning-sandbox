---
name: modify-existing-module
description: Assess and revise an existing learning-sandbox module. Use when changing its learning outcomes, prerequisites, scope, or exercise sequence.
---

# Modify an existing module

Improve the module's progression while preserving learner work. Start with the requested learning outcome and the module's current scope.

## Assess and propose

Read the module overview, relevant public exercise briefs, and the authoring context required by `AGENTS.md`. Check related modules when the proposal may duplicate material or change prerequisites.

Identify what the learner can already practice and what is missing. Distinguish a gap in practice from a gap in explanation or a problem with an existing exercise. For each proposed exercise, state what it teaches, where it fits, what the learner will submit, and how that work will be checked.

Design the exercise sequence before assigning numbers. The numeric prefix of each exercise directory is its ID and must match its position in the module's learning order. Keep the sequence contiguous. If an insertion, removal, or move changes the order, include the old and new IDs of all affected exercises in the proposal. Get agreement on scope and any changes to exercise behavior or grading before implementing a proposal. Proceed with changes the user has already approved.

## Revise and verify

Follow the repository conventions for exercise briefs, scaffolds, fixtures, and validators. When an exercise changes number, move its entire directory with its scaffold, learner submission, notes, and tests. Carry its progress and checkpoint entries to the new position. Preserve its grading contract unless the approved revision changes it. Flag any completed exercise that needs rechecking.

Update the module overview, specification, progress list, and all affected references to exercise numbers and paths. Check validator selectors, fixtures, command examples, prerequisites, and links from other modules. Update registration and generation state when the approved change affects them. Verify that each changed ID resolves to the intended exercise, including when a new exercise reuses an old number.

Run the applicable authoring checks from `AGENTS.md` and report any verification limits. Use isolated service resources when checks recreate or tear down data. Identify which teaching material the revision affects. Once the revised module is verified, use [author-module-lectures](../author-module-lectures/SKILL.md) for a separate request to plan or write its teaching material.
