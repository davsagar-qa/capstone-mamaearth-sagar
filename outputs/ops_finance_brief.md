# Mamaearth returns brief — regional ops & finance

_Generator: deterministic_template. Numbers grounded against `outputs/metrics.json`._



*Every figure below is copied from `outputs/metrics.json`, which was computed from `sql/reports.sql` on `mamaearth.db`. No external numbers.*

## 1. Verdict

Returns are a real margin leak, not a rounding error. Of 180 orders, 45 came back (25.0% of orders) and reversed ₹28791.1 of discounted GMV — 28.83% of net GMV (₹99860.2). Realised net after reversing those returns is ₹71069.1.

The leak is concentrated: the top 5 returned orders account for 42.43% of returned net GMV. Treat this as a subset problem (specific cities, COD, a few SKUs, and two quantity-outlier rows), not a brand-wide quality collapse.

## 2. Where the rupees leak

- **City:** Lucknow (tier 2) contributes ₹14953.7 of returned net on 15 of 49 orders (30.61% return rate). Jaipur has the highest city return rate at 42.11% (8 of 19 orders).
- **City tier:** Tier 1 return rate is 19.64% (₹10568.4 leaked). Tier 2 is 33.82% (₹18222.7 leaked).
- **Category:** Babycare is the largest rupee leak (₹9950.7, 23.33% of 30 orders). Highest category return *rate* is Skincare at 31.67%.
- **SKU:** Milky Soft Baby Lotion (P11, Babycare) leaked ₹8073.0 across 2 of 17 orders (11.76%).
- **Payment:** COD return rate is 43.64% vs prepaid 16.8% (26.84 pp higher). COD leaked ₹18298.3. Card 14.29%, UPI 20.0%.
- **Experience:** Orders rated 1–2 return at 31.15%; orders rated 4–5 return at 17.91%.
- **Acquisition:** Highest return rate by source is Ad at 32.08% (17 of 53 orders).

Largest single reverse: O0011 — Isha in Lucknow, Milky Soft Baby Lotion, qty 25, COD, ₹7475.0.

## 3. Noise vs signal

- **Quantity outliers:** O0098 is qty 30 (net ₹10470.0, returned=0). Outlier returned net is ₹7475.0 (25.96% of all returned net). Do not set a national return-rate target off these two rows.
- **Duplicate fingerprints:** 5 extra rows share a customer/product/date/qty/payment fingerprint. Finance should strip them before board reporting.
- **Orders before signup:** 87 orders have `order_date` earlier than `signup_date` — a CRM/join issue, not a fulfilment issue.
- **Nulls (correctly stored as NULL, not empty strings):** 12 missing `discount_pct`, 15 missing `rating`. Empty-string ratings: 0. Rated orders in the headline: 165; average rating 3.02.

## 4. Actions

1. **Ops — Lucknow COD + Babycare outlier.** O0011 alone is ₹7475.0. Freeze COD on qty>5 until a second review, and audit Lucknow reverse logistics. Supporting: Lucknow leaked ₹14953.7; COD return rate 43.64%.
2. **Finance — restate net after returns and duplicates.** Publish realised net ₹71069.1 (net GMV ₹99860.2 minus returned ₹28791.1) and flag 5 duplicate extra rows so margin packs are not inflated.
3. **Ops — SKU and prepaid mix.** Put Milky Soft Baby Lotion on a return watch (₹8073.0 leaked, 11.76% of its 17 orders). Shift at-risk cities from COD toward UPI/Card where prepaid returns sit at 16.8%.

## 5. What not to do

Do not blame a single category for a company-wide quality failure: Babycare rupee leak is dominated by O0011 (quantity 25, ₹7475.0). Do not treat missing ratings as zeros — 165 of 180 orders have a rating. Do not set discount policy from this sample alone; use the discount-band table in `outputs/metrics.json` before cutting promo depth.
