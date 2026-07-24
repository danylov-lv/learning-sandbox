-- Task 02: category-tree-rollup
-- Expected output columns (in order): root_category, subtree_category_count, leaf_count, max_depth, product_count, product_share_pct
-- Write your query below.
with recursive category_tree as (
    select c.id, c.parent_id, c.name, c.level, c.id as root_id, c.name as root_category
    from categories c
    where c.level = 0
    
    union all

    select cc.id, cc.parent_id, cc.name, cc.level, ct.root_id, ct.root_category
    from categories cc
    inner join category_tree ct on cc.parent_id = ct.id
)
select ct.root_category,
 count(distinct ct.id) as "subtree_category_count",
 count(distinct case 
    when ct.id not in (select distinct parent_id from categories where parent_id is not null)
    then ct.id 
 end) as "leaf_count",
 max(ct.level) as "max_depth",
 count(distinct p.id) as "product_count",
 round((count(distinct p.id) * 100.0) / sum(count(distinct p.id)) over (), 2) as "product_share_pct"
from category_tree ct
left join products p on p.category_id = ct.id
group by ct.root_category

