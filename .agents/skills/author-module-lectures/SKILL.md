---
name: author-module-lectures
description: Plan, write, revise, or resume a module's lecture course and prepare focused reading guides for its exercises.
---

# Author module lectures

Build a course around what learners need to understand and do by the end of the module. Teach reusable concepts, methods, and patterns in the shared course. Exercises give learners practice applying them independently.

## Plan the course

Read the module overview, project conventions, and existing lecture index. Establish the learner's starting point and the module outcomes. Draft the chapter sequence from those outcomes and their conceptual prerequisites. Give prerequisites their own coverage when later material depends on them, even when no exercise tests them directly. Link to existing material where it already provides the foundation.

Group material by what learners need to understand together. A reusable pattern can be a section in a broader chapter, part of a collection of related patterns, or a chapter in its own right when the learning outcome warrants it.

Use the module's `Lectures.md` as the course index. Give each chapter a learning outcome, a stable path, and any prerequisite reading. Mark planned chapters and link to published chapters from the index. Link the index from the module overview. With no chapter layout already in use, use `lectures/NN-topic.md` for chapters.

Check the draft against the public exercise briefs and show where practice fits. If an exercise exposes a missing reusable concept, place its explanation in the shared course. For a planning request, deliver the outline and flag version-sensitive topics or open technical questions for verification during chapter writing.

## Write the material

For a shared chapter, explain the concept, the decisions it informs, and the conditions that affect those decisions. Use a self-contained example with its own scenario and data. Show intermediate results where they help the learner follow the reasoning. Add a short self-check when useful. Leave the graded exercise for the learner to solve.

For an exercise reading guide, link to the specific sections the learner needs and say what to take from each. A few annotated links can be the complete guide. Put additional material beside the exercise only when a task-specific detail needs its own explanation.

## Verify and resume

Consult primary sources for technical claims. Use documentation and release notes for the version used in the module, specifications or original research for protocols and algorithms, and maintainer guidance or published engineering case studies for engineering practices. Use web search to find public sources when needed. Link to the relevant source sections in the chapter and tie recommendations to the conditions and evidence that support them.

Run executable examples in the documented environment and check the stated results. Run the project's applicable authoring checks. Record what remains unverified if a source or environment is unavailable.

After a change, update the index and record pending verification and the next chapter in the existing tracker or the index. On resume, use the requested target or select the next planned chapter whose prerequisites are ready.
