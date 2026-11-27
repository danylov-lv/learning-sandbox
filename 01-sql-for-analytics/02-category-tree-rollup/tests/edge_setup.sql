INSERT INTO categories (id, name, parent_id, level) VALUES
    (1, 'Alpha', NULL, 0),
    (2, 'Beta', NULL, 0),
    (3, 'Gamma', NULL, 0),
    (4, 'Delta', NULL, 0),
    (5, 'Epsilon', NULL, 0),
    (6, 'Zeta', NULL, 0),
    (7, 'Eta', NULL, 0),
    (8, 'Theta', NULL, 0),
    (11, 'Alpha shallow', 1, 1),
    (12, 'Alpha branch', 1, 1),
    (13, 'Alpha section', 12, 2),
    (14, 'Alpha group', 13, 3),
    (15, 'Alpha deep', 14, 4),
    (21, 'Beta branch', 2, 1),
    (22, 'Beta leaf', 21, 2);

INSERT INTO products (id, name, category_id, brand, first_seen_at) VALUES
    (101, 'Alpha root product', 1, 'Sample', '2025-01-01'),
    (102, 'Alpha shallow product', 11, 'Sample', '2025-01-01'),
    (103, 'Alpha deep product', 15, 'Sample', '2025-01-01'),
    (104, 'Alpha group product', 14, 'Sample', '2025-01-01'),
    (201, 'Beta branch product', 21, 'Sample', '2025-01-01'),
    (202, 'Beta leaf product', 22, 'Sample', '2025-01-01');
