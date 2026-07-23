# 19 — TypeScript Track

## What this track covers

Advanced TypeScript as a **type and contract system**, not "JavaScript with
types". This track assumes you already ship production TypeScript — NestJS
services, Next.js apps — so there is no intro material: no "what is an
interface", no `tsc` basics. Every task pushes on the parts of the language
you can ship a career without ever touching directly: the type-level
programming that libraries do for you, runtime-validated contracts at the
edges, and sharing a single source of truth across a monorepo.

Three tasks, standalone-paced (pick this up alongside the main track):

- **01 type-challenges** — a progression of type-level puzzles solved in the
  type system itself, graded by the compiler.
- **02 type-safe-sdk-client** — a validated SDK for a module-12-shaped
  marketplace API, where the types are inferred from runtime schemas so a
  malformed response is a thrown error, not a silent lie.
- **03 capstone-monorepo-contracts** — one `contracts` package whose types
  and schemas flow into an `api`, a `worker`, and a `web` client, with `e2e`
  tests that only pass when the whole graph agrees.

## Stack

This is a **pnpm workspace** (a real monorepo — that is thematically
deliberate for the capstone). There is no Python, no `docker-compose.yml`,
and no host ports: the workspace plus `tsc --noEmit` and `vitest` replace all
of that. See `.authoring/design.md` for why this is the module's documented
exception to the repo-wide conventions.

All dev dependencies (`typescript`, `vitest`, `zod`, `@types/node`, `tsx`)
live once in the root `package.json`; every package links them through the
workspace, so a task never touches root dependencies or re-runs
`pnpm install`.

Prerequisites:

- Node (v24 was used to build this; anything modern with `fetch` works).
- pnpm via corepack: `corepack enable` (or install pnpm directly). The
  committed `pnpm-lock.yaml` pins exact resolved versions.

## Getting started

```bash
cd 19-ts-track
pnpm install
```

That one install links every package in the graph. You should not need to run
it again while working through the tasks.

## Running a task's validator

Each package exposes two scripts. From the module root, target a package by
its name:

```bash
pnpm --filter @sandbox19/t01 run typecheck   # tsc --noEmit, strict
pnpm --filter @sandbox19/t02 run test         # vitest run
```

A type error or a failing test exits non-zero with a clean message — that is
this module's stand-in for the repo-wide "print `NOT PASSED: <reason>` and
exit 1, no raw tracebacks" convention. `pnpm -r run typecheck` and
`pnpm -r run test` run the whole workspace at once.

The shared given infrastructure lives in `@sandbox19/harness`: type-level test
utilities (`Expect`, `Equal`, …) and a tiny deterministic HTTP mock server for
the SDK and capstone tasks. Depend on it; never re-implement it.

## Tasks

| # | Task | Package(s) | Evenings |
|---|------|-----------|:---:|
| 01 | type-challenges | `@sandbox19/t01` | 1–2 |
| 02 | type-safe-sdk-client | `@sandbox19/t02` | 2–3 |
| 03 | capstone-monorepo-contracts | `@t3/contracts`, `@t3/api`, `@t3/worker`, `@t3/web`, `@t3/e2e` | 3–4 |

- **01** — a graded progression of type-challenge puzzles (utility types,
  conditional and mapped types, recursion, inference). Solved purely in the
  type system; the compiler is the grader.
- **02** — build a type-safe client for the marketplace API the harness mock
  server serves: pagination, auth with token refresh, and schema-validated
  responses so the deliberately-malformed routes throw instead of returning
  garbage typed as valid.
- **03** (capstone) — define shared contracts once and consume them across an
  API, a worker, and a web client, with `e2e` checkpoints (CP1/CP2/CP3) that
  fail if any package drifts from the contract.

## No reference solutions

As with every module in this repo, there are no reference solutions anywhere —
not in hints, not in `.authoring/`, not in tests. Per-task `hints/` narrow
from a direction to a mechanism to near-pseudocode, but never hand you working
code.

## `.authoring/` is off-limits until after a task

`.authoring/design.md` documents the harness API contract and the grading
philosophy behind every task. Reading it before you finish a task spoils it.
Read it afterward, if at all — same rule as every other module.
