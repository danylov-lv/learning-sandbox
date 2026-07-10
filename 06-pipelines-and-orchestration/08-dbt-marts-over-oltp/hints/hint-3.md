# Hint 3

Rough shape for `mart_daily_category_gmv.sql` (fill in the real column
names from your own staging views — this is pseudocode, not something to
paste in):

```
with lines as (
    select
        order_id, quantity, unit_price
    from stg_order_items
),
qualifying_orders as (
    select id, created_at::date as order_date
    from stg_orders
    where status not in ('pending', 'cancelled')
)
select
    qo.order_date,
    category.family as category_family,
    sum(l.quantity * l.unit_price) as gmv,
    count(distinct qo.id) as order_count
from lines l
join qualifying_orders qo on qo.id = l.order_id
join <product staging> ... join <category staging> ...
group by 1, 2
```

Rough shape for `fct_order_line_items.sql`:

```
{{ config(materialized='incremental', unique_key='order_item_id') }}

select
    oi.id as order_item_id,
    oi.order_id,
    o.created_at,
    ...
from stg_order_items oi
join stg_orders o on o.id = oi.order_id
{% if is_incremental() %}
where o.created_at > (select coalesce(max(created_at), '1900-01-01') from {{ this }})
{% endif %}
```

Custom generic test skeleton for `macros/custom_tests.sql` — pick a rule
that's actually meaningful for this data (e.g. GMV should never be
negative, or an order_count should never be zero on a row that exists):

```
{% test gmv_is_non_negative(model, column_name) %}
select *
from {{ model }}
where {{ column_name }} < 0
{% endtest %}
```

then in `schema.yml`, under that column: `tests: [gmv_is_non_negative]`.
