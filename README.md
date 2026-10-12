# Mamaearth Growth Analytics — returns vs margin

Three connected layers. No layer reports a number it did not compute itself or receive from the layer before it.

```
data/*.csv
    -> sql/schema.sql + sql/seed_data.sql   -> mamaearth.db
    -> sql/reports.sql                      -> outputs/sql_extracts/*.csv
    -> analysis/analyze.py                  -> outputs/metrics.json
    -> narrative/generate_brief.py          -> outputs/ops_finance_brief.md
```

Run everything:

```bash
python run_pipeline.py
```

That command:

1. Regenerates `sql/seed_data.sql` from the CSVs (blank `discount_pct` / `rating` become SQL `NULL`).
2. Rebuilds `mamaearth.db` and asserts `customers=45`, `products=16`, `orders=180`.
3. Executes the named reports in `sql/reports.sql`.
4. Derives concentration, COD vs prepaid, and data-quality flags only from those result sets.
5. Writes an ops/finance brief. If `OPENAI_API_KEY` is set it calls the Chat Completions API at temperature 0; otherwise it fills a grounded template. Either path is rejected if a number appears that is not in `metrics.json`.

## SQL store

| File | Role |
|---|---|
| `sql/schema.sql` | `customers`, `products`, `orders` with PK/FK, `returned INT NOT NULL DEFAULT 0` |
| `sql/generate_seed.py` | Builds INSERT statements from CSVs |
| `sql/seed_data.sql` | Re-runnable seed (generated) |
| `sql/cleanup_nulls.sql` | Use only if you loaded via SQLite `.import` (empty strings → NULL) |
| `sql/reports.sql` | Count, rating-by-category, leakage by category/city/payment/SKU |

Report (b) uses `COUNT(rating)` / `AVG(rating)`, which ignore `NULL`. Empty strings would be counted as present — the seed INSERTs and the post-import cleanup both prevent that.

## Analysis layer

Reads the database, not the raw CSVs, for published metrics. Headline question: **which subset of orders is eating discounted GMV via returns?**

## Narrative layer

Audience: regional ops and finance heads. The brief is in `outputs/ops_finance_brief.md` after a pipeline run.

## Seed check

```sql
SELECT COUNT(*) FROM customers;  -- 45
SELECT COUNT(*) FROM products;   -- 16
SELECT COUNT(*) FROM orders;     -- 180
```
