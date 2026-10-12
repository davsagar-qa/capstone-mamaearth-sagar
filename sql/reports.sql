-- Mamaearth SQL reporting layer.
-- Every metric here is computed from the relational store after seed load.
-- Python analysis must consume these result sets; it may not invent replacement numbers.

PRAGMA foreign_keys = ON;

-- REPORT: a_row_counts
SELECT 'customers' AS table_name, COUNT(*) AS row_count FROM customers
UNION ALL
SELECT 'products', COUNT(*) FROM products
UNION ALL
SELECT 'orders', COUNT(*) FROM orders;

-- REPORT: b_rating_by_category
-- COUNT(rating) ignores NULL ratings. Empty strings must already be cleaned to NULL.
SELECT
    p.category,
    COUNT(*) AS orders,
    COUNT(o.rating) AS rated_orders,
    ROUND(AVG(o.rating), 2) AS avg_rating
FROM orders o
JOIN products p ON p.product_id = o.product_id
GROUP BY p.category
ORDER BY avg_rating ASC;

-- REPORT: c_headline_kpis
SELECT
    COUNT(*) AS orders,
    SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) AS returned_orders,
    ROUND(100.0 * SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS return_rate_pct,
    ROUND(SUM(o.quantity * p.price), 2) AS gross_gmv,
    ROUND(SUM(o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0)), 2) AS net_gmv,
    ROUND(SUM(CASE WHEN o.returned = 1 THEN o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0) ELSE 0 END), 2) AS returned_net_gmv,
    ROUND(
        100.0 * SUM(CASE WHEN o.returned = 1 THEN o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0) ELSE 0 END)
        / SUM(o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0)),
        2
    ) AS returned_net_share_pct,
    COUNT(o.rating) AS rated_orders,
    ROUND(AVG(o.rating), 2) AS avg_rating
FROM orders o
JOIN products p ON p.product_id = o.product_id;

-- REPORT: d_category_margin_leakage
SELECT
    p.category,
    COUNT(*) AS orders,
    SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) AS returned_orders,
    ROUND(100.0 * SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS return_rate_pct,
    ROUND(SUM(o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0)), 2) AS net_gmv,
    ROUND(SUM(CASE WHEN o.returned = 1 THEN o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0) ELSE 0 END), 2) AS returned_net_gmv,
    ROUND(
        100.0 * SUM(CASE WHEN o.returned = 1 THEN o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0) ELSE 0 END)
        / SUM(o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0)),
        2
    ) AS returned_net_share_pct
FROM orders o
JOIN products p ON p.product_id = o.product_id
GROUP BY p.category
ORDER BY returned_net_gmv DESC;

-- REPORT: e_payment_method
SELECT
    UPPER(o.payment_method) AS payment_method,
    COUNT(*) AS orders,
    SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) AS returned_orders,
    ROUND(100.0 * SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS return_rate_pct,
    ROUND(SUM(o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0)), 2) AS net_gmv,
    ROUND(SUM(CASE WHEN o.returned = 1 THEN o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0) ELSE 0 END), 2) AS returned_net_gmv
FROM orders o
JOIN products p ON p.product_id = o.product_id
GROUP BY UPPER(o.payment_method)
ORDER BY return_rate_pct DESC;

-- REPORT: f_city_tier
SELECT
    c.city_tier,
    COUNT(*) AS orders,
    SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) AS returned_orders,
    ROUND(100.0 * SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS return_rate_pct,
    ROUND(SUM(o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0)), 2) AS net_gmv,
    ROUND(SUM(CASE WHEN o.returned = 1 THEN o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0) ELSE 0 END), 2) AS returned_net_gmv
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN products p ON p.product_id = o.product_id
GROUP BY c.city_tier
ORDER BY c.city_tier;

-- REPORT: g_city
SELECT
    c.city,
    c.city_tier,
    COUNT(*) AS orders,
    SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) AS returned_orders,
    ROUND(100.0 * SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS return_rate_pct,
    ROUND(SUM(o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0)), 2) AS net_gmv,
    ROUND(SUM(CASE WHEN o.returned = 1 THEN o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0) ELSE 0 END), 2) AS returned_net_gmv
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN products p ON p.product_id = o.product_id
GROUP BY c.city, c.city_tier
ORDER BY returned_net_gmv DESC;

-- REPORT: h_discount_band
SELECT
    CASE
        WHEN o.discount_pct IS NULL THEN 'missing'
        WHEN o.discount_pct = 0 THEN '0'
        WHEN o.discount_pct <= 10 THEN '1-10'
        WHEN o.discount_pct <= 20 THEN '11-20'
        ELSE '21-30'
    END AS discount_band,
    COUNT(*) AS orders,
    SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) AS returned_orders,
    ROUND(100.0 * SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS return_rate_pct,
    ROUND(SUM(CASE WHEN o.returned = 1 THEN o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0) ELSE 0 END), 2) AS returned_net_gmv
FROM orders o
JOIN products p ON p.product_id = o.product_id
GROUP BY
    CASE
        WHEN o.discount_pct IS NULL THEN 'missing'
        WHEN o.discount_pct = 0 THEN '0'
        WHEN o.discount_pct <= 10 THEN '1-10'
        WHEN o.discount_pct <= 20 THEN '11-20'
        ELSE '21-30'
    END
ORDER BY discount_band;

-- REPORT: i_product_leakage
SELECT
    p.product_id,
    p.product_name,
    p.category,
    COUNT(*) AS orders,
    SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) AS returned_orders,
    ROUND(100.0 * SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS return_rate_pct,
    ROUND(SUM(o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0)), 2) AS net_gmv,
    ROUND(SUM(CASE WHEN o.returned = 1 THEN o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0) ELSE 0 END), 2) AS returned_net_gmv
FROM orders o
JOIN products p ON p.product_id = o.product_id
GROUP BY p.product_id, p.product_name, p.category
ORDER BY returned_net_gmv DESC;

-- REPORT: j_rating_vs_return
SELECT
    CASE WHEN o.rating IS NULL THEN 'unrated' ELSE CAST(o.rating AS TEXT) END AS rating_bucket,
    COUNT(*) AS orders,
    SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) AS returned_orders,
    ROUND(100.0 * SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS return_rate_pct,
    ROUND(SUM(CASE WHEN o.returned = 1 THEN o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0) ELSE 0 END), 2) AS returned_net_gmv
FROM orders o
JOIN products p ON p.product_id = o.product_id
GROUP BY CASE WHEN o.rating IS NULL THEN 'unrated' ELSE CAST(o.rating AS TEXT) END
ORDER BY rating_bucket;

-- REPORT: k_acquisition_source
SELECT
    c.acquisition_source,
    COUNT(*) AS orders,
    SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) AS returned_orders,
    ROUND(100.0 * SUM(CASE WHEN o.returned = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS return_rate_pct,
    ROUND(SUM(CASE WHEN o.returned = 1 THEN o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0) ELSE 0 END), 2) AS returned_net_gmv
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN products p ON p.product_id = o.product_id
GROUP BY c.acquisition_source
ORDER BY return_rate_pct DESC;

-- REPORT: l_quantity_outliers
SELECT
    o.order_id,
    o.customer_id,
    c.city,
    p.product_name,
    o.order_date,
    o.quantity,
    o.payment_method,
    o.rating,
    o.returned,
    ROUND(o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0), 2) AS net_gmv
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN products p ON p.product_id = o.product_id
WHERE o.quantity > 5
ORDER BY o.quantity DESC;

-- REPORT: m_returned_orders
SELECT
    o.order_id,
    o.customer_id,
    c.name AS customer_name,
    c.city,
    c.city_tier,
    p.product_id,
    p.product_name,
    p.category,
    o.order_date,
    o.quantity,
    o.discount_pct,
    UPPER(o.payment_method) AS payment_method,
    o.rating,
    ROUND(o.quantity * p.price * (1.0 - COALESCE(o.discount_pct, 0) / 100.0), 2) AS returned_net_gmv
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN products p ON p.product_id = o.product_id
WHERE o.returned = 1
ORDER BY returned_net_gmv DESC;

-- REPORT: n_duplicate_fingerprints
SELECT
    o.customer_id,
    o.product_id,
    o.order_date,
    o.quantity,
    o.discount_pct,
    UPPER(o.payment_method) AS payment_method,
    o.rating,
    o.returned,
    COUNT(*) AS copy_count,
    GROUP_CONCAT(o.order_id) AS order_ids
FROM orders o
GROUP BY
    o.customer_id,
    o.product_id,
    o.order_date,
    o.quantity,
    o.discount_pct,
    UPPER(o.payment_method),
    o.rating,
    o.returned
HAVING COUNT(*) > 1
ORDER BY copy_count DESC, o.order_date;

-- REPORT: o_orders_before_signup
SELECT
    o.order_id,
    o.customer_id,
    c.name,
    c.signup_date,
    o.order_date,
    o.returned
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.order_date < c.signup_date
ORDER BY o.order_date;

-- REPORT: p_null_audit
SELECT
    SUM(CASE WHEN discount_pct IS NULL THEN 1 ELSE 0 END) AS null_discount_pct,
    SUM(CASE WHEN rating IS NULL THEN 1 ELSE 0 END) AS null_rating,
    SUM(CASE WHEN typeof(discount_pct) = 'text' AND discount_pct = '' THEN 1 ELSE 0 END) AS empty_string_discount_pct,
    SUM(CASE WHEN typeof(rating) = 'text' AND rating = '' THEN 1 ELSE 0 END) AS empty_string_rating
FROM orders;
