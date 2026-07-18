# Capstone Design Memo — End-to-End Enrichment Pipeline

Fill in each section with your own analysis, grounded in what you actually
built and measured across CP1 (`src/pipeline.py`, `src/explain.py`) and
CP2 (the same `src/pipeline.py` under chaos input) of this capstone. Cite
real numbers your own runs produced (per-field accuracy, macro-F1,
pairwise F1, quarantine rate, catalog precision, runtime) — not numbers you
expect or numbers from this template.

## Pipeline architecture

[fill in — describe how `run_pipeline` composes `extract_record`,
`classify_record`, and `dedup_cluster`: what each stage consumes and
produces, and why the three input sets (extraction/classification/dedup)
stay independent rather than chained (extraction's output doesn't feed
classification's input, etc.) — what would change about the pipeline's
shape if you DID chain them end to end over one shared record stream
instead?]

## Quality / confidence gate

[fill in — how does `extract_record` / `classify_record` / `dedup_cluster`
compute its own `confidence`, and what threshold(s) decide `valid`? Cite
your own measured quarantine rate on CLEAN input (CP1) — why does a gate
that's too aggressive on clean input fail the capstone's requirements just
as much as a gate that's too lax under chaos (CP2)?]

## Chaos handling and graceful degradation

[fill in — what does CP2 actually corrupt (cite the HTML corruption
fraction and the injected-junk call rate from `validate_cp2.py`), and how
does your pipeline avoid crashing on either? Cite your own measured catalog
precision and quarantine recall under chaos — which one was harder to hit,
and why? What's the difference between "the gate quarantined a record" and
"the gate silently produced a wrong answer that landed in the clean
catalog," and which failure mode is worse for a real downstream consumer of
this catalog?]

## RAG explain-product step

[fill in — how does `explain_product` build its retrieval corpus from the
catalog, and how many candidates does it retrieve before generating an
answer? Cite your own measured citation hit-rate and answer-contains-fact
rate from CP1. Why is citing the wrong product but stating a technically-
true fact about it still a failure for this feature, and does your
`_answer_contains_fact`-style check (or the validator's) actually catch
that case?]

## Metrics and thresholds

[fill in — list the actual threshold each CP1/CP2 metric had to clear
(extraction per-field accuracy, classification macro-F1, dedup pairwise
F1, quarantine rate, catalog precision, quarantine recall, explain hit/
answer rate) and your own measured value next to each. Which metric had
the least headroom above its threshold, and why do you think that stage is
the pipeline's weakest link?]

## Scaling and production considerations

[fill in — this pipeline runs against a 7B local model over ~50-80 records
per stage in a few minutes. What would change (batching, caching,
concurrency, model choice, retry/backoff, the confidence-gate thresholds
themselves) if this had to enrich a real catalog of a few million rows on a
recurring schedule? What would you monitor in production to catch the
gate silently drifting (e.g. quarantine rate creeping up after a model or
prompt change) before it affects downstream consumers of the clean
catalog?]
