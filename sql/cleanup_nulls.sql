-- Required if you load via SQLite .import instead of INSERT statements.
-- .import stores blank discount_pct / rating cells as empty strings, not NULL.
-- COUNT(rating) would then count those strings as present and break Report (b).

UPDATE orders SET discount_pct = NULL WHERE TRIM(CAST(discount_pct AS TEXT)) = '';
UPDATE orders SET rating = NULL WHERE TRIM(CAST(rating AS TEXT)) = '';
