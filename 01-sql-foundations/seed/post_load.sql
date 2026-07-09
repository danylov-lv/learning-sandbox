-- Constraints and indexes added after bulk COPY (bulk validation is much faster).

ALTER TABLE categories
    ADD CONSTRAINT fk_categories_parent FOREIGN KEY (parent_id) REFERENCES categories(id);
ALTER TABLE products
    ADD CONSTRAINT fk_products_category FOREIGN KEY (category_id) REFERENCES categories(id);
ALTER TABLE price_snapshots
    ADD CONSTRAINT fk_snapshots_product FOREIGN KEY (product_id) REFERENCES products(id),
    ADD CONSTRAINT fk_snapshots_source FOREIGN KEY (source_id) REFERENCES sources(id);

CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_categories_parent ON categories(parent_id);
CREATE INDEX idx_snapshots_product_time ON price_snapshots(product_id, captured_at);
CREATE INDEX idx_snapshots_source_time ON price_snapshots(source_id, captured_at);

ANALYZE;
