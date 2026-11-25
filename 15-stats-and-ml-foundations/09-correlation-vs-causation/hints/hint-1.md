A strong correlation between two variables tells you they move together.
It does not tell you *why* -- and one very common "why" that has nothing to
do with either variable causing the other is a third variable that happens
to move both of them in the same direction.

Before writing any code, ask: who else differs systematically across the
rows of this dataset, in a way that could plausibly push BOTH
`discount_pct` and `units_sold` in the same direction at once? Not every
column is a candidate -- `seller_rating` or `source_site`, for instance,
have no obvious story connecting them to how deeply something gets
discounted. Think about which column groups products into buckets that
differ in both "how aggressively is this kind of product typically
discounted" and "how many units does this kind of product typically move,
independent of any discount."
