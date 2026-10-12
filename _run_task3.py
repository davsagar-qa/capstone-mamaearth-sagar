import sqlite3
from pathlib import Path

root = Path(r"d:\Mamaearth")
conn = sqlite3.connect(root / "mamaearth.db")
conn.executescript((root / "sql" / "schema.sql").read_text(encoding="utf-8"))
conn.executescript((root / "sql" / "seed_data.sql").read_text(encoding="utf-8"))
conn.row_factory = sqlite3.Row


def show(title: str, sql: str) -> None:
    print("=" * 72)
    print(title)
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = [tuple(r) for r in cur.fetchall()]
    print(" | ".join(cols))
    print(f"rows={len(rows)}")
    for r in rows:
        print(" | ".join("" if v is None else str(v) for v in r))


show(
    "a",
    """
SELECT COUNT(*) AS total_orders,
       ROUND(SUM(o.quantity * p.price * (1 - COALESCE(o.discount_pct, 0) / 100.0)), 2) AS total_revenue,
       ROUND(SUM(o.quantity * p.price * (1 - COALESCE(o.discount_pct, 0) / 100.0)) * 1.0 / COUNT(*), 2) AS avg_order_value
FROM orders o
JOIN products p ON p.product_id = o.product_id;
""",
)

show(
    "b",
    """
SELECT COUNT(*) AS count_star,
       COUNT(rating) AS count_rating,
       COUNT(*) - COUNT(rating) AS missing_ratings
FROM orders;
""",
)

show(
    "c1",
    """
SELECT c.customer_id, c.name, COUNT(o.order_id) AS order_count
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.name
HAVING COUNT(o.order_id) = 0;
""",
)

show(
    "c2",
    """
SELECT customer_id, name
FROM customers
WHERE customer_id NOT IN (SELECT DISTINCT customer_id FROM orders);
""",
)

show(
    "d",
    """
SELECT c.city,
       COUNT(*) AS total_orders,
       SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) AS returned_orders,
       ROUND(100.0 * SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS return_rate_pct
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
GROUP BY c.city
HAVING return_rate_pct > 20
ORDER BY return_rate_pct DESC;
""",
)

show(
    "e5",
    """
SELECT c.customer_id, c.name,
       ROUND(SUM(o.quantity * p.price * (1 - COALESCE(o.discount_pct, 0) / 100.0)), 2) AS total_spend
FROM orders o
JOIN products p ON p.product_id = o.product_id
JOIN customers c ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.name
ORDER BY total_spend DESC, c.customer_id ASC
LIMIT 5;
""",
)

show(
    "eoff",
    """
SELECT c.customer_id, c.name,
       ROUND(SUM(o.quantity * p.price * (1 - COALESCE(o.discount_pct, 0) / 100.0)), 2) AS total_spend
FROM orders o
JOIN products p ON p.product_id = o.product_id
JOIN customers c ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.name
ORDER BY total_spend DESC, c.customer_id ASC
LIMIT 3 OFFSET 2;
""",
)

show(
    "f",
    """
SELECT p.category,
       COUNT(*) AS order_count,
       ROUND(SUM(o.quantity * p.price * (1 - COALESCE(o.discount_pct, 0) / 100.0)), 2) AS category_revenue
FROM orders o
JOIN products p ON p.product_id = o.product_id
JOIN customers c ON c.customer_id = o.customer_id
GROUP BY p.category
ORDER BY category_revenue DESC;
""",
)

show(
    "g",
    """
SELECT customer_id, name, city, city_tier, signup_date, acquisition_source
FROM customers
WHERE name LIKE 'A%'
ORDER BY customer_id;
""",
)

show(
    "h",
    """
SELECT DISTINCT acquisition_source
FROM customers
ORDER BY acquisition_source;
""",
)

conn.execute("ALTER TABLE customers ADD COLUMN loyalty_tier VARCHAR(10);")
conn.execute(
    "UPDATE customers SET loyalty_tier = CASE WHEN city_tier = 1 THEN 'Gold' ELSE 'Silver' END;"
)
show(
    "i",
    """
SELECT loyalty_tier, COUNT(*) AS n
FROM customers
GROUP BY loyalty_tier
ORDER BY loyalty_tier;
""",
)
