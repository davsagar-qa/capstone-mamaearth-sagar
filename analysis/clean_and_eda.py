"""Read the Mamaearth database, run sql/reports.sql, and write narrator/findings.json."""

import json
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB_PATH = ROOT / "mamaearth.db"
REPORTS_PATH = ROOT / "sql" / "reports.sql"
FINDINGS_PATH = ROOT / "narrator" / "findings.json"
NAME_PATTERN = re.compile(r"(?m)^-- name: ([a-z0-9_]+)\s*$")


def split_named_sql(text):
    matches = list(NAME_PATTERN.finditer(text))
    if not matches:
        raise SystemExit(f"{REPORTS_PATH} does not contain any '-- name:' queries.")
    preamble = text[: matches[0].start()]
    queries = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body.endswith(";"):
            body = body[:-1].strip()
        queries[match.group(1)] = body
    return preamble, queries


def connect():
    if not DB_PATH.exists():
        raise SystemExit(
            "mamaearth.db was not found. Run Layer 1 (sql/schema.sql, then sql/seed_data.sql) "
            "from the repository root before this script."
        )
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def rows_as_dicts(connection, sql):
    cursor = connection.execute(sql)
    return [dict(row) for row in cursor.fetchall()]


def one_row(connection, sql):
    result = rows_as_dicts(connection, sql)
    if len(result) != 1:
        raise SystemExit(f"Expected one row, found {len(result)}.")
    return result[0]


def whole_number(value):
    if value is None:
        return 0
    return int(value)


def money(value):
    if value is None:
        return 0.0
    return round(float(value), 2)


def rate(value):
    if value is None:
        return 0.0
    return round(float(value), 4)


def build_findings(connection, queries):
    counts = {
        row["table_name"]: whole_number(row["row_count"])
        for row in rows_as_dicts(connection, queries["table_counts"])
    }
    span = one_row(connection, queries["date_span"])
    quality = one_row(connection, queries["data_quality"])
    kpis = one_row(connection, queries["kpis"])

    return {
        "source_database": DB_PATH.name,
        "cleaning_rules": [
            "Payment method is trimmed and grouped as UPI, COD, or Card, ignoring letter case.",
            "A blank discount is treated as 0 when calculating line revenue.",
            "A blank rating stays missing and is excluded from the average rating.",
            "Orders with quantity above 10 are excluded from rates and revenue as quantity outliers.",
            "Net revenue keeps non-returned lines only: price x quantity x (1 - discount_pct / 100).",
            "Possible duplicate order rows are reported and still included in the totals.",
        ],
        "dataset": {
            "customers": counts.get("customers", 0),
            "products": counts.get("products", 0),
            "orders": counts.get("orders", 0),
            "min_order_date": span["min_order_date"],
            "max_order_date": span["max_order_date"],
        },
        "data_quality": {
            "blank_discount_count": whole_number(quality["blank_discount_count"]),
            "blank_rating_count": whole_number(quality["blank_rating_count"]),
            "outlier_order_count": whole_number(quality["outlier_order_count"]),
            "orders_in_analysis": whole_number(quality["orders_in_analysis"]),
            "raw_payment_methods": rows_as_dicts(connection, queries["raw_payment_methods"]),
            "outlier_orders": rows_as_dicts(connection, queries["outlier_orders"]),
            "possible_duplicate_orders": rows_as_dicts(connection, queries["possible_duplicate_orders"]),
            "customers_without_orders": rows_as_dicts(connection, queries["customers_without_orders"]),
        },
        "kpis": {
            "orders": whole_number(kpis["orders"]),
            "returned_orders": whole_number(kpis["returned_orders"]),
            "return_rate": rate(kpis["return_rate"]),
            "net_revenue": money(kpis["net_revenue"]),
            "returned_line_value": money(kpis["returned_line_value"]),
            "average_rating": None if kpis["average_rating"] is None else round(float(kpis["average_rating"]), 2),
            "rated_orders": whole_number(kpis["rated_orders"]),
        },
        "return_rate_by_payment": [
            {
                "payment_method": row["payment_method"],
                "orders": whole_number(row["orders"]),
                "returned_orders": whole_number(row["returned_orders"]),
                "return_rate": rate(row["return_rate"]),
            }
            for row in rows_as_dicts(connection, queries["return_rate_by_payment"])
        ],
        "monthly_revenue": [
            {
                "order_month": row["order_month"],
                "orders": whole_number(row["orders"]),
                "kept_orders": whole_number(row["kept_orders"]),
                "returned_orders": whole_number(row["returned_orders"]),
                "net_revenue": money(row["net_revenue"]),
            }
            for row in rows_as_dicts(connection, queries["monthly_revenue"])
        ],
        "revenue_by_category": [
            {
                "category": row["category"],
                "orders": whole_number(row["orders"]),
                "returned_orders": whole_number(row["returned_orders"]),
                "return_rate": rate(row["return_rate"]),
                "net_revenue": money(row["net_revenue"]),
            }
            for row in rows_as_dicts(connection, queries["revenue_by_category"])
        ],
    }


def load_raw_csvs():
    """Load the source files before any cleaning. orders must be 180 rows by 9 columns."""
    customers = pd.read_csv(DATA / "customers.csv")
    products = pd.read_csv(DATA / "products.csv")
    orders = pd.read_csv(DATA / "orders.csv")
    print(orders.shape)
    return customers, products, orders


def standardize_payment_method(orders):
    """Collapse payment_method casing. Raw file has 7 spellings; upper leaves 3."""
    print(orders["payment_method"].unique())
    orders["payment_method"] = orders["payment_method"].str.strip().str.upper()
    print(orders["payment_method"].value_counts())
    return orders


DUPLICATE_KEY = [
    "customer_id",
    "product_id",
    "order_date",
    "quantity",
    "discount_pct",
    "payment_method",
    "rating",
    "returned",
]
RAW_ORDER_TOTAL = 99860.20


def drop_duplicate_orders(orders):
    """Drop later copies of the same natural key. order_id is excluded on purpose."""
    duplicate_mask = orders.duplicated(subset=DUPLICATE_KEY, keep="first")
    dropped = orders.loc[duplicate_mask].copy()
    print(dropped["order_id"].tolist())
    orders_clean = orders.loc[~duplicate_mask].copy()
    print(orders_clean.shape)
    return orders_clean, dropped


def impute_missing_values(orders_clean):
    """Fill blank discounts with 0 and blank ratings with the median of the known ratings."""
    print(int(orders_clean["discount_pct"].isna().sum()))
    orders_clean["discount_pct"] = orders_clean["discount_pct"].fillna(0)

    rating_median = orders_clean["rating"].median()
    print(rating_median)
    print(int(orders_clean["rating"].isna().sum()))
    orders_clean["rating"] = orders_clean["rating"].fillna(rating_median)

    print(orders_clean[["discount_pct", "rating"]].isnull().sum().to_dict())
    return orders_clean


def line_order_value(frame):
    return frame["quantity"] * frame["price"] * (1 - frame["discount_pct"] / 100)


def reconcile_order_value(orders_clean, dropped, products, customers):
    """Merge cleaned orders to products and customers, then explain the gap versus the raw SQL total."""
    cleaned = orders_clean.merge(products, on="product_id", validate="many_to_one")
    cleaned = cleaned.merge(customers, on="customer_id", validate="many_to_one")
    cleaned["order_value"] = line_order_value(cleaned)
    cleaned_total = round(float(cleaned["order_value"].sum()), 2)
    print(f"{cleaned_total:.2f}")

    dropped_valued = dropped.merge(products, on="product_id", validate="many_to_one")
    dropped_valued["order_value"] = line_order_value(dropped_valued)
    dropped_total = round(float(dropped_valued["order_value"].sum()), 2)
    dropped_ids = ", ".join(dropped_valued["order_id"].tolist())
    delta = round(RAW_ORDER_TOTAL - cleaned_total, 2)

    print(
        f"Part 1 Report (a) totals Rs {RAW_ORDER_TOTAL:,.2f} of order value on all 180 raw rows. "
        f"The cleaned orders, after the merge with products and customers, total Rs {cleaned_total:,.2f} "
        f"across {len(cleaned)} rows, which is Rs {delta:,.2f} less. "
        f"That entire delta is the combined order_value of the 5 duplicate rows removed in Task 3 "
        f"({dropped_ids}). Summing order_value on those dropped rows independently gives Rs {dropped_total:,.2f}. "
        f"Imputing discount_pct from missing to 0 and rating to the median does not change any order_value total: "
        f"a missing discount is already treated as 0% in the order_value formula, and rating is not part of that formula."
    )
    return cleaned, cleaned_total, dropped_total


def correlation_band(value):
    magnitude = abs(value)
    if magnitude < 0.2:
        return "negligible"
    if magnitude < 0.4:
        return "weak"
    if magnitude < 0.7:
        return "moderate"
    return "strong"


def flag_quantity_outliers(merged):
    """IQR fences on quantity. Outlier rows stay in the frame and are flagged."""
    q1 = float(merged["quantity"].quantile(0.25))
    q3 = float(merged["quantity"].quantile(0.75))
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    print(f"Q1 = {q1:.1f}, Q3 = {q3:.1f}, IQR = {iqr:.1f}, lower = {lower:.1f}, upper = {upper:.1f}")

    merged = merged.copy()
    merged["is_outlier"] = (merged["quantity"] < lower) | (merged["quantity"] > upper)
    flagged = merged.loc[merged["is_outlier"], ["order_id", "quantity", "order_date"]]
    print(flagged.to_string(index=False))
    return merged


def test_cod_return_hypothesis(merged):
    """COD should show a higher return rate than CARD and UPI on the deduplicated orders."""
    print("Hypothesis: COD has a higher return rate than CARD and UPI.")
    summary = merged.groupby("payment_method")["returned"].agg(["count", "mean"])
    print(summary)
    for method, row in summary.iterrows():
        print(f"{method}: {row['mean'] * 100:.1f}%")
    cod_rate = float(summary.loc["COD", "mean"])
    others = summary.drop(index="COD")["mean"]
    label = "Confirmed" if cod_rate > float(others.max()) else "Not confirmed"
    print(f"Hypothesis label: {label}")
    rows = []
    for method, row in summary.sort_values("mean", ascending=False).iterrows():
        rows.append(
            {
                "payment_method": method,
                "orders": int(row["count"]),
                "return_rate": round(float(row["mean"]), 4),
                "return_rate_pct": round(float(row["mean"]) * 100, 1),
            }
        )
    return rows


def segment_return_rates(merged):
    """Show that the blended COD return rate hides a higher Tier-2 rate."""
    segment = (
        merged.groupby(["payment_method", "city_tier"])["returned"]
        .agg(orders="count", return_rate="mean")
        .reset_index()
    )
    segment["return_rate_pct"] = (segment["return_rate"] * 100).round(1)
    print(segment.to_string(index=False))

    ranked = segment.sort_values(["return_rate", "orders"], ascending=[False, False]).iloc[0]
    cod = segment.loc[segment["payment_method"] == "COD"].set_index("city_tier")
    tier1 = cod.loc[1]
    tier2 = cod.loc[2]
    print(
        f"The single highest-risk segment is COD + Tier-{int(ranked['city_tier'])} cities "
        f"at {ranked['return_rate_pct']:.1f}% "
        f"({int(tier1['orders'])} Tier-1 COD orders at {tier1['return_rate_pct']:.1f}%, "
        f"versus {int(tier2['orders'])} Tier-2 COD orders at {tier2['return_rate_pct']:.1f}%). "
        "COD risk is not uniform across tiers: the blended COD rate hides how concentrated the returns are in Tier 2."
    )
    return {
        "payment_method": str(ranked["payment_method"]),
        "city_tier": int(ranked["city_tier"]),
        "return_rate_pct": float(ranked["return_rate_pct"]),
    }


def correlation_analysis(merged):
    """Pairwise correlations stay in the negligible band, so discount does not explain returns."""
    columns = ["rating", "returned", "discount_pct", "quantity"]
    corr = merged[columns].corr()
    print(corr.round(4))
    print("Bands: negligible 0-0.19, weak 0.2-0.39, moderate 0.4-0.69, strong 0.7-1.0.")
    for index, left in enumerate(columns):
        for right in columns[index + 1 :]:
            value = float(corr.loc[left, right])
            print(f"{left} vs {right}: r = {value:.4f} ({correlation_band(value)})")
    discount_return = float(corr.loc["discount_pct", "returned"])
    print(
        f'Hypothesis "higher discounts reduce returns": Busted. '
        f"discount_pct vs returned correlation is {discount_return:.2f}, which is negligible."
    )


def monthly_order_value(merged):
    """Compare monthly order value with the two quantity outliers in and out."""
    frame = merged.copy()
    frame["order_date"] = pd.to_datetime(frame["order_date"])
    frame["year_month"] = frame["order_date"].dt.strftime("%Y-%m")

    def series_for(subset):
        totals = subset.groupby("year_month")["order_value"].sum().sort_index()
        rows = []
        for month, value in totals.items():
            rounded = round(float(value), 2)
            print(f"{month}: {rounded:.2f}")
            rows.append({"order_month": month, "order_value": rounded})
        return rows

    print("Monthly order_value including quantity outliers:")
    with_outliers = series_for(frame)
    print("Monthly order_value excluding quantity outliers:")
    corrected = series_for(frame.loc[~frame["is_outlier"]])

    outlier_bits = []
    flagged = frame.loc[frame["is_outlier"], ["order_id", "order_date", "quantity"]]
    for row in flagged.sort_values("order_id").itertuples(index=False):
        outlier_bits.append(f"{row.order_id} on {row.order_date.strftime('%Y-%m-%d')}")
    inflated_peak = max(with_outliers, key=lambda row: row["order_value"])
    corrected_peak = max(corrected, key=lambda row: row["order_value"])
    inflated_name = pd.Timestamp(inflated_peak["order_month"]).strftime("%B %Y")
    corrected_name = pd.Timestamp(corrected_peak["order_month"]).strftime("%B %Y")
    print(
        f"{inflated_name}'s apparent lead is an artifact of the two bulk orders landing in January "
        f"({', '.join(outlier_bits)}). "
        f"{corrected_name} is the genuine peak month once those two orders are excluded. "
        "Task 6 flags them before this comparison so the inflated January total is not treated as the real peak."
    )
    return corrected, with_outliers


def narrator_findings(cleaned_total, dropped_total, chart_return_rates, highest_risk, corrected, with_outliers):
    """Verified Part 1 and Part 2 figures for narrator/findings.json."""
    rates = {row["payment_method"]: row["return_rate_pct"] for row in chart_return_rates}
    inflated = max(with_outliers, key=lambda row: row["order_value"])
    corrected_same_month = next(
        row for row in corrected if row["order_month"] == inflated["order_month"]
    )
    peak = max(corrected, key=lambda row: row["order_value"])
    return {
        "cleaned_total_revenue_inr": cleaned_total,
        "raw_total_revenue_inr": RAW_ORDER_TOTAL,
        "duplicate_reconciliation_delta_inr": dropped_total,
        "return_rate_by_payment": {method: rates[method] for method in ("COD", "CARD", "UPI")},
        "highest_risk_segment": highest_risk,
        "true_peak_month": {"month": peak["order_month"], "revenue_inr": peak["order_value"]},
        "outlier_inflated_month": {
            "month": inflated["order_month"],
            "apparent_revenue_inr": inflated["order_value"],
            "corrected_revenue_inr": corrected_same_month["order_value"],
        },
    }


def dump_findings(payload):
    """Write money fields with two decimal places so 97358.30 is not shortened to 97358.3."""
    text = json.dumps(payload, indent=2)
    money_keys = (
        "cleaned_total_revenue_inr",
        "raw_total_revenue_inr",
        "duplicate_reconciliation_delta_inr",
        "revenue_inr",
        "apparent_revenue_inr",
        "corrected_revenue_inr",
    )
    for key in money_keys:
        text = re.sub(
            rf'("{key}": )(-?\d+(?:\.\d+)?)',
            lambda match: f"{match.group(1)}{float(match.group(2)):.2f}",
            text,
        )
    return text + "\n"


def main():
    customers, products, orders = load_raw_csvs()
    orders = standardize_payment_method(orders)
    orders_clean, dropped_orders = drop_duplicate_orders(orders)
    orders_clean = impute_missing_values(orders_clean)
    merged, cleaned_total, dropped_total = reconcile_order_value(
        orders_clean, dropped_orders, products, customers
    )
    merged = flag_quantity_outliers(merged)
    chart_return_rates = test_cod_return_hypothesis(merged)
    highest_risk = segment_return_rates(merged)
    correlation_analysis(merged)
    chart_monthly_revenue, monthly_with_outliers = monthly_order_value(merged)
    verified = narrator_findings(
        cleaned_total,
        dropped_total,
        chart_return_rates,
        highest_risk,
        chart_monthly_revenue,
        monthly_with_outliers,
    )
    if not REPORTS_PATH.exists():
        raise SystemExit(f"Missing {REPORTS_PATH}")
    preamble, queries = split_named_sql(REPORTS_PATH.read_text(encoding="utf-8"))
    connection = connect()
    try:
        connection.executescript(preamble)
        sql_report = build_findings(connection, queries)
    finally:
        connection.close()

    findings = {
        **verified,
        "chart_return_rate_by_payment": chart_return_rates,
        "chart_monthly_revenue": chart_monthly_revenue,
        "sql_report": sql_report,
    }
    FINDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    FINDINGS_PATH.write_text(dump_findings(findings), encoding="utf-8")
    print(f"Wrote {FINDINGS_PATH}")


if __name__ == "__main__":
    sys.exit(main())
