A concrete shape for `run_pipeline`, still deliberately incomplete --
you fill in every real line, including the pacer (see task 01/05's hints
for the self-calibrating-pacer pattern if you haven't built one yet; the
gotcha is identical here: bounded concurrency alone does not cap your
throughput on this target).

```
run_pipeline(client_id, day, chaos, workdir):
    metrics.build_registry()   # idempotent -- safe if this is the 2nd call this process
    workdir = workdir or DEFAULT_WORKDIR
    workdir.mkdir(parents=True, exist_ok=True)

    client = build a browser-like client, X-Client-Id=client_id
    ids = discover_product_ids(client, day, chaos)

    clean_rows, quarantine_rows = [], []
    n_rendered = 0
    completeness_tracker = {field: [0, 0] for field in TRACKED_FIELDS}  # [present, total]

    for id in ids, paced + bounded-concurrency (see task 01/05):
        t0 = now()
        html = fetch_product_html(client, id, day, chaos)
        metrics.record_fetch("html", now() - t0)

        fields = extract_fields(html, id)
        record = {"id": id, **fields, "rating": None, "shipping_info": None}

        is_clean, reason = quality_check(record)
        if not is_clean:
            metrics.record_quarantine(defect_type_from(reason))

        if fields["review_count"] and fields["review_count"] > 0:
            t1 = now()
            detail = fetch_product_detail(client, id, day)
            metrics.record_fetch("api", now() - t1)
            record["rating"] = detail.get("rating")
            record["shipping_info"] = detail.get("shipping_info")
            if record["rating"] is not None and record["shipping_info"] is not None:
                n_rendered += 1

        update completeness_tracker from record
        (clean_rows if is_clean else quarantine_rows).append(
            record if is_clean else {**record, "reason": reason}
        )

    write clean_rows -> workdir/clean.jsonl
    write quarantine_rows -> workdir/quarantine.jsonl
    for field, (present, total) in completeness_tracker.items():
        metrics.set_field_completeness(field, present / total)
    metrics.set_banned(get this client's current banned state)

    required = [r for r in clean_rows + quarantine_rows if r["review_count"] and r["review_count"] > 0]
    rendered = [r for r in required if r["rating"] is not None and r["shipping_info"] is not None]
    completeness = len(rendered) / len(required) if required else 1.0
    modeled_cost = len(ids) * HTTP_COST + n_rendered * API_EXTRA_COST

    summary = {"ids": sorted(ids), "clean_count": len(clean_rows), ...}
    write summary -> workdir/summary.json
    return summary
```

For the idempotent-recovery behavior CP2 checks: the simplest correct
`changed_between` is stateless -- fetch both days fresh every call, from
scratch, no cross-call state at all. That is trivially idempotent (nothing
persists to drift) and is a perfectly valid implementation; you do NOT need
to build real crash-resume/checkpoint machinery to pass CP2. If you DO want
the incremental optimization (persisting a fingerprint index under `run/`
so a later call can skip re-fetching an already-known day), make sure a
partially-written index file (as if a previous run had been interrupted
mid-write) still leaves you with a fully correct result on the next call --
e.g. by writing the index file atomically (write to a temp path, then
rename) rather than appending to it incrementally.
