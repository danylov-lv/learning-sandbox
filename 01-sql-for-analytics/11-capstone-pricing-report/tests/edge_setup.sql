INSERT INTO sources (id, name, country, tier, currency) VALUES
    (1, 'Sample EUR', 'DE', 1, 'EUR'),
    (2, 'Sample USD', 'US', 2, 'USD');

INSERT INTO categories (id, name, parent_id, level) VALUES
    (1, 'Electronics', NULL, 0),
    (2, 'Books', NULL, 0),
    (11, 'Audio', 1, 1),
    (12, 'Home audio', 11, 2),
    (13, 'Speakers', 12, 3);

INSERT INTO products (id, name, category_id, brand, first_seen_at) VALUES
    (101, 'General electronics', 1, 'Sample', '2025-01-01'),
    (102, 'Audio component', 11, 'Sample', '2025-01-01'),
    (103, 'Speaker', 13, 'Sample', '2025-01-01'),
    (201, 'Book', 2, 'Sample', '2025-01-01');

INSERT INTO exchange_rates (currency, rate_date, rate_to_usd) VALUES
    ('EUR', '2025-01-01', 2.0),
    ('EUR', '2025-01-03', 3.0),
    ('EUR', '2025-02-01', 4.0),
    ('USD', '2025-01-01', 1.0),
    ('USD', '2025-02-01', 1.0);

INSERT INTO price_snapshots (id, product_id, source_id, captured_at, price, currency, in_stock) VALUES
    (1, 101, 1, '2025-01-01 04:00:00', 5.00, 'EUR', true),
    (2, 102, 1, '2025-01-02 04:00:00', 10.00, 'EUR', false),
    (3, 103, 1, '2025-01-03 04:00:00', 8.00, 'EUR', true),
    (4, 101, 2, '2025-01-03 04:00:00', 30.00, 'USD', true),
    (5, 101, 1, '2025-02-01 04:00:00', 10.00, 'EUR', true),
    (6, 102, 1, '2025-02-02 04:00:00', 20.00, 'EUR', false),
    (7, 201, 2, '2025-01-01 04:00:00', 0.00, 'USD', false),
    (8, 201, 2, '2025-02-01 04:00:00', 10.00, 'USD', true);
