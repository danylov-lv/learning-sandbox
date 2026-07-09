-- Claim contract (see README "What's given" for the full spec):
--   Claim up to %(batch_size)s pending rows from payments_queue_arena for
--   worker %(worker_id)s: move them to status = 'claimed', record who
--   claimed them, and RETURN the claimed ids.
--
-- This is the STOCK starting point, not a solution. Rewrite this file.

UPDATE payments_queue_arena
SET status = 'claimed',
    claimed_by = %(worker_id)s,
    claimed_at = now()
WHERE id IN (
    SELECT id
    FROM payments_queue_arena
    WHERE status = 'pending'
    ORDER BY id
    LIMIT %(batch_size)s
    FOR UPDATE
)
RETURNING id
