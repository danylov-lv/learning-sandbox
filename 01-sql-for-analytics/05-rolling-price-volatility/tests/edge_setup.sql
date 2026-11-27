INSERT INTO sources (id, name, country, tier, currency) VALUES
    (91, 'Sample 91', 'US', 1, 'USD'),
    (113, 'Sample 113', 'US', 2, 'USD'),
    (186, 'Sample 186', 'US', 3, 'USD');

INSERT INTO categories (id, name, parent_id, level) VALUES
    (1, 'Sample', NULL, 0);

INSERT INTO products (id, name, category_id, brand, first_seen_at) VALUES
    (17943, 'Product 17943', 1, 'Sample', '2025-01-01'),
    (22654, 'Product 22654', 1, 'Sample', '2025-01-01'),
    (72050, 'Product 72050', 1, 'Sample', '2025-01-01'),
    (140857, 'Product 140857', 1, 'Sample', '2025-01-01'),
    (157376, 'Product 157376', 1, 'Sample', '2025-01-01');

INSERT INTO price_snapshots (id, product_id, source_id, captured_at, price, currency, in_stock) VALUES
    (1, 140857, 186, '2025-01-01 00:00:00', 100.00, 'USD', true),
    (2, 140857, 186, '2025-01-31 00:00:00', 60.00, 'USD', true),
    (3, 140857, 186, '2025-01-31 00:00:01', 60.00, 'USD', true),
    (4, 140857, 91, '2025-01-15 00:00:00', 40.00, 'USD', true),
    (5, 140857, 113, '2025-01-15 00:00:00', 50.00, 'USD', true),
    (6, 157376, 186, '2025-01-15 00:00:00', 65.00, 'USD', true),
    (7, 157376, 91, '2025-01-15 00:00:00', 35.00, 'USD', true),
    (8, 157376, 113, '2025-01-15 00:00:00', 45.00, 'USD', true),
    (9, 72050, 113, '2025-01-15 00:00:00', 20.00, 'USD', true),
    (10, 17943, 113, '2025-01-15 00:00:00', 15.00, 'USD', true),
    (11, 17943, 91, '2025-01-15 00:00:00', 10.00, 'USD', true),
    (12, 22654, 186, '2025-01-15 00:00:00', 25.00, 'USD', true);
