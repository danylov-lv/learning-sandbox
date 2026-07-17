Don't start by writing `run_pipeline`. Start by writing the five functions
it's built from, and prove each one works in isolation against a handful of
product ids before you ever wire them together into a full-catalog run.

`discover_product_ids`, `fetch_product_html`, `extract_fields`,
`fetch_product_detail`, and `quality_check` are each testable on their own
with a plain script and a handful of ids -- you already built the concepts
behind every one of them in tasks 01/04/02/05. The capstone's actual new
work is the WIRING: deciding, for each product id, in what order these five
things happen, and what state (clean vs. quarantine, rendered vs. not) each
one's output determines for the next step.

Sketch the per-product flow on paper before writing `run_pipeline`:

```
id -> fetch_product_html -> extract_fields -> quality_check
                                             \
                                              -> review_count > 0? -> fetch_product_detail
```

Notice `quality_check` and the render decision are INDEPENDENT branches off
the same extracted record -- a product can be quarantined AND rendered (a
bad_currency defect doesn't touch `review_count`), or clean and never
rendered (`review_count == 0`). Don't couple them; a bug where "quarantined
implies never rendered" (or vice versa) will fail CP1's completeness check
in a way that's confusing to debug if you didn't design the branch
independence in deliberately.

Get a 20-product slice working end to end -- discovery, extraction, gate,
router, metrics -- and inspect the output files by eye before ever pointing
`run_pipeline` at the full ~4,000-product catalog.
