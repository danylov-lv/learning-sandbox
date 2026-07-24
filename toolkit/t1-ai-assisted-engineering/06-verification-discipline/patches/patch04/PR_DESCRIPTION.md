# Add chunk() helper for batched API calls

## Summary

The bulk-export job needs to call a downstream provider API that caps
requests at a maximum batch size. Adds a `chunk()` helper to split an
arbitrary list into fixed-size batches before sending.

## Details

- `chunk(items, size)` returns a list of lists, each of at most `size`
  elements; the final chunk may be smaller.
- Raises `ValueError` on a non-positive `size` rather than looping
  forever or returning something silently wrong.

## Testing

`chunk(list(range(7)), 3)` -> `[[0,1,2],[3,4,5],[6]]`.
`chunk([], 3)` -> `[]`. `chunk(list(range(6)), 3)` -> `[[0,1,2],[3,4,5]]`
(exact multiple, no trailing empty chunk).
