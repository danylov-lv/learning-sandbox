# Simplify feature-flag lookup

## Summary

`is_feature_enabled()` had a small if/else chain handling a couple of
legacy config shapes. This simplifies it to a single `bool()` coercion of
the raw config value, since Python already treats missing/falsy values
correctly.

## Details

- `config.get(key, False)` -- defaults to disabled when the key is
  absent, same as before.
- Wrapped in `bool()` so any truthy/falsy raw value normalizes to an
  actual `bool` for the caller, instead of leaking whatever type the
  config source happened to hand back.

## Testing

`is_feature_enabled({}, "x")` -> `False`,
`is_feature_enabled({"x": True}, "x")` -> `True`. Both match the old
behavior.
