# Hint 1

Your task-01 schema most likely has `shops.tier` and `products.brand` as
plain columns you overwrite on update — that's fine for "what's true now,"
but it destroys the previous value the moment a `shop_tier_changed` or
`product_attrs_changed` event lands. To answer "what was true then" you need
somewhere the old value keeps living after it stops being current.

The standard shape for this is a validity interval instead of a single
value: not "this shop's tier is gold" but "this shop's tier was gold from
[some point] until [some other point]." Where do those intervals come from?
You already have them, in the event stream you loaded for task 01 — every
tier change, every rename, every attribute change is an event with an
`event_time`. Think of the history table as one row per (entity, value,
interval) rather than one row per entity.
