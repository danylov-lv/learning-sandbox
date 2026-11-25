No ready-made test code -- just the concrete list of cases worth having,
function by function. Turn each of these into its own test (a precise
`assert x == <exact value>` or `pytest.raises(ValueError)`, not a vague
"doesn't crash" check):

**`apply_discount`**
- A normal discount, checked against the exact expected number (kills
  arithmetic-operator swaps in the formula).
- `pct=0.0` and `pct=100.0`, the two ends of the valid range.
- `price` and `pct` chosen so the discounted amount lands BELOW
  `min_price`, confirming the result is the floor, not the raw discount.
- `price < 0.0` raising, and `price == 0.0` NOT raising.
- `pct < 0.0` raising, and `pct > 100.0` raising -- separately, since
  they're two different conditions joined by `or`.

**`classify_price_tier`**
- One value comfortably inside each of the four tiers.
- The exact price at each of the three tier boundaries (`20.0`, `100.0`,
  `500.0`), asserting it lands in the TIER ABOVE the boundary, not below --
  that's what pins down `<` vs `<=` at each cutoff.

**`is_valid_sku`**
- A valid SKU at the minimum digit count and one at the maximum.
- One invalid case per individual check, changing only that one thing
  from an otherwise-valid SKU: wrong letter case, wrong letter count (too
  few AND too many), wrong digit count (too few AND too many), non-digit
  characters where digits belong, no hyphen at all, and a second hyphen
  landing inside what should be the digit run.

**`shipping_cost`**
- A normal cost, checked against the exact expected number.
- The same inputs with `express=True`, checked against a DIFFERENT exact
  number.
- `weight_kg == 0.0` raising (it's `<=`, not `<`), and a small positive
  weight not raising.
- `distance_km` negative raising, and `distance_km == 0.0` NOT raising.
- Inputs small enough that the computed subtotal would be below the
  minimum charge, confirming the result is the floor -- try this both with
  and without `express=True`, since the floor applies after the
  multiplier.

If, after all of that, `cosmic-ray`'s own survivor list still shows a
`core/ReplaceComparisonOperator_*_Is` or `*_IsNot` entry, that one is
excluded from what `validate.py` grades -- see the README's note on
equivalent mutants. Everything else on the list is yours to kill.
