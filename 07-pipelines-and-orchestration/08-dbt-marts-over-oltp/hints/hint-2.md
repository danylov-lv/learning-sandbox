# Hint 2

For the aggregate mart: build it as a `group by` over a join of your
`stg_order_items` and `stg_orders` staging views (join to `stg_products`
and `stg_categories` to get from a line item to its category family) —
never join straight to `source(...)` from a mart. The GMV filter is
`status not in ('pending', 'cancelled')`; get this exact clause into the
`where` (or into a `case`/filtered aggregate) or the validator's
independent recomputation won't match yours.

For the incremental mart, the standard shape is:

```sql
select ...
from {{ ref('stg_order_items') }} oi
join {{ ref('stg_orders') }} o on ...
{% if is_incremental() %}
where o.created_at > (select max(created_at) from {{ this }})
{% endif %}
```

`{{ this }}` refers to the mart's own existing table — only valid inside an
incremental model, and only meaningful after the first build has created
it.

For the custom generic test: a generic test is just a macro named
`test_<something>` in `macros/`, referenced from `schema.yml` the same way
you'd reference `not_null`. It must `select` rows that violate the rule —
dbt treats a non-empty result as a test failure.
