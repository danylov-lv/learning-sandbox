`ROW_NUMBER()` never duplicates a value within a partition — it just assigns
1, 2, 3, ... in the order defined by its `ORDER BY`, arbitrarily breaking
ties by row order unless you tell it otherwise. Put the tiebreak column
directly in that `ORDER BY`, after the price: `ORDER BY max_price DESC,
product_id ASC`. That's what makes rank 3 always pick exactly one product
even when several tie on price.

Separately, you'll need to join `categories` to itself enough times to walk
from a level-3 leaf up to its level-2 ancestor, then down from a chosen
level-0 root to find which leaves are in scope.
