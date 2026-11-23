# Prompt: add a new sandbox module

Fill in the three INPUT placeholders, then submit this prompt in Codex from the repository root. This also supports the second-wave topics in README.

---

I want to extend the sandbox with a NEW module. Do not modify existing modules or their tasks — this is purely additive.

## INPUT

- **Topic**: {TOPIC, for example Cassandra, Terraform, or network layer for scraping}
- **My starting point & motivation**: {WHAT I KNOW AND WHY I NEED THIS, 1-3 sentences to calibrate difficulty}
- **Size**: {small: 4-6 single-evening tasks / standard: 8-12 tasks plus capstone / deep: 12+ tasks and multi-evening capstone}

## Process (follow strictly, in this order)

1. **Read the global sections of docs/authoring/SPEC.md** (everything before "# Module specs") — the philosophy, collaboration rules, task format, quality requirements, and my profile apply: the learner writes solutions, hints have three tiers, verification is objective, environments are module-specific, materials are in English, and tasks include NOTES.md templates. Read CONVENTIONS.md for track-specific exceptions.
2. **Skim existing module titles** (grep "## MODULE:" in docs/authoring/SPEC.md) to avoid overlap. If the topic partially overlaps an existing module, the new module must reference and build on it, not duplicate it (e.g., a wide-column module reuses generated datasets and contrasts with the existing NoSQL/OLAP modules rather than re-teaching them).
3. **Draft the module spec** in the same style and density as existing "## MODULE:" sections: backstory flavored to my domain (scraping/price data where natural), task list easy→hard, capstone if size warrants, verification approach per task type, cross-references to existing modules where infrastructure can be reused. Calibrate difficulty to my starting point from INPUT.
4. **Show me the draft spec and WAIT for my approval.** Do not generate anything before I confirm. Expect edits.
5. After approval: **append the approved spec to docs/authoring/SPEC.md** as a new "## MODULE:" section (assign the next free number, or a track prefix if it fits an existing track), **add it to docs/authoring/GENERATION_STATE.md** as pending, update the root README learning map and PROGRESS.md.
6. **Generate the module** per the standard process: decompose the work, delegate independent parts only when useful and supported, review all changes, verify the required environments and validators, and mark done in docs/authoring/GENERATION_STATE.md only after recording the actual verification results and any limitations. Do not include learner solutions.

## Constraints

- Everything must run on my hardware (32 GB RAM, RTX 3070 Ti 8 GB, Docker on Windows) — if the topic implies heavyweight infra (e.g., a real Cassandra ring), design the local approximation honestly and add one written task about what differs at production scale.
- New datasets only via seeded generator scripts; reuse existing generated data where it fits.
- If the topic is fast-moving (AI tooling, cloud services), verify current state of the tools against documentation before writing tasks — no invented features.
