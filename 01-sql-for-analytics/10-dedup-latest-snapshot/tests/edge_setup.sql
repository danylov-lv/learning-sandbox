INSERT INTO sources (id, name, country, tier, currency) VALUES
    (1, 'Sample USD', 'US', 1, 'USD'),
    (2, 'Sample EUR', 'DE', 2, 'EUR');

INSERT INTO categories (id, name, parent_id, level) VALUES
    (1, 'Sample', NULL, 0);

INSERT INTO products (id, name, category_id, brand, first_seen_at) VALUES
    (101, 'First product', 1, 'Sample', '2025-01-01'),
    (102, 'Second product', 1, 'Sample', '2025-01-01');

INSERT INTO price_snapshots (id, product_id, source_id, captured_at, price, currency, in_stock) VALUES
    (11, 101, 1, '2025-01-02 12:00:00', 80.00, 'USD', false),
    (12, 101, 1, '2025-01-02 12:00:00', 20.00, 'USD', true),
    (13, 101, 1, '2025-01-01 12:00:00', 100.00, 'USD', false),
    (21, 102, 1, '2025-01-02 12:00:00', 40.00, 'USD', false),
    (31, 101, 2, '2025-01-02 12:00:00', 50.00, 'EUR', true),
    (32, 101, 2, '2025-01-02 12:00:00', 60.00, 'EUR', false);
