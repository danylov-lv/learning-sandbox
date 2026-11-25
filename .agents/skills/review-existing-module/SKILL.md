---
name: review-existing-module
description: Review an existing learning-sandbox module for teaching quality, exercise progression, grading correctness, and technical currency. Use when the learner wants to assess a module before deciding whether to revise it.
---

# Review an existing module

Assess the module as it exists today. Keep repository files read-only. Use isolated services and temporary files for runtime checks.

Read the module overview, its specification, the learner's starting point, and applicable project conventions. Use the public exercise briefs in learning order to identify the intended outcomes and the important guarantees the module makes. Inspect scaffolds, fixtures, validators, and related modules where they provide evidence about those outcomes or guarantees.

## Validate the learning path

Follow the learner's path from the prerequisites to the final outcome. Check whether the supplied materials let the learner start, whether their work develops the intended skill, and whether each major outcome gets practice. Identify where the sequence supports learning and where it leaves a gap or spends effort on incidental setup. Trace capstone demands to earlier exercises and check how available teaching material prepares learners for independent practice.

## Verify the implementation

Compare the briefs with the documented setup, scaffolds, fixtures, and graders. Check whether correct behavior passes, plausible mistakes are caught, and any required technique has observable evidence. Run targeted checks where the environment is available. Treat the expected rejection of an unsolved scaffold as normal. Use primary sources for version-sensitive claims and flag technical drift that affects how the learner runs or understands the exercise.

## Check the scope of findings

For a material finding, restate the learning outcome or guarantee it affects and identify the mechanism or assumption behind the failure. Check nearby stages, input cases, or exercises that rely on the same mechanism. Use the evidence to distinguish a local defect from a shared one. When reviewing a fix, recheck the underlying guarantee across those related cases.

After following a finding, return to the remaining learning outcomes and exercise contracts. Review each part in proportion to its impact on the learner. Record which related cases you confirmed and which still need verification.

## Give an overall assessment

Judge how well the module teaches its intended skills and how usable it is today. Cite concrete strengths and any shortcomings, with their locations, evidence, and effects on the learner. State what you inspected, what you ran, and where the evidence is incomplete. Keep exercise solutions and fixture answers out of the report.

Propose a revision when the evidence warrants it, from a focused correction to a redesign of the module. Explain the outcome the revision should achieve, the strengths it should preserve, and how to assess its result. If the learner approves a revision, use the report as input to [modify-existing-module](../modify-existing-module/SKILL.md).
