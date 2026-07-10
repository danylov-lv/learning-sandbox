# Hint 1

Get the plumbing working before writing any real model SQL: an empty
`select 1` in each stub, `dbt build`, and check with `\dn` and `\dt
dbt_analytics_marts.*` inside module 02's Postgres that everything landed
where you expect and nothing landed in `public`. Only once the schema
isolation is confirmed should you start filling in real logic — much
cheaper to catch a misconfigured schema now than after you've written five
models against the wrong target.

Think about the incremental mart's failure mode before you write it: what
happens if you materialize it as `incremental` but never call
`is_incremental()` anywhere in the model? Run `dbt build` twice early and
watch the row count.
