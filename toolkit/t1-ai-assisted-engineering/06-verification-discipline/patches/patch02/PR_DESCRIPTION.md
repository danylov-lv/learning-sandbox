# Add paginate() helper for /records

## Summary

The `/records` endpoint needs server-side pagination now that the table
has grown past a few thousand rows. Adds a small `paginate()` helper used
by the endpoint's query-param handler (`page`, `page_size`).

## Details

- 0-indexed `page`.
- Straightforward slicing: compute a `start`/`end` offset pair from
  `page` and `page_size`, slice the list.

## Testing

Manually checked `paginate(list(range(20)), 0, 5)` and
`paginate(list(range(20)), 1, 5)` against the old client-side pagination
logic's output for the same inputs -- results matched.
