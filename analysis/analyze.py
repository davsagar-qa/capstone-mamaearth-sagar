from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"
OUTPUTS = ROOT / "outputs"
EXTRACTS = OUTPUTS / "sql_extracts"
DB_PATH = ROOT / "mamaearth.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def split_reports(sql_text: str) -> list[tuple[str, str]]:
    reports: list[tuple[str, str]] = []
    current_name = "preamble"
    chunks: list[str] = []
    for line in sql_text.splitlines():
        if line.startswith("-- REPORT:"):
            body = "\n".join(chunks).strip()
            if body:
                reports.append((current_name, body))
            current_name = line.split(":", 1)[1].strip()
            chunks = []
        else:
            chunks.append(line)
    body = "\n".join(chunks).strip()
    if body:
        reports.append((current_name, body))
    return [(name, stmt) for name, stmt in reports if name != "preamble"]


def json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def rows_to_records(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [{k: json_safe(v) for k, v in dict(row).items()} for row in rows]


def execute_reports(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    EXTRACTS.mkdir(parents=True, exist_ok=True)
    report_sql = (SQL_DIR / "analysis_reports.sql").read_text(encoding="utf-8")
    results: dict[str, list[dict[str, Any]]] = {}
    for name, stmt in split_reports(report_sql):
        cur = conn.execute(stmt)
        records = rows_to_records(cur.fetchall())
        results[name] = records
        write_csv(EXTRACTS / f"{name}.csv", records)
    return results


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    import csv

    if not records:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)


def one(records: list[dict[str, Any]]) -> dict[str, Any]:
    if len(records) != 1:
        raise ValueError(f"Expected 1 row, got {len(records)}")
    return records[0]


def share(part: float | None, whole: float | None, digits: int = 2) -> float | None:
    if part is None or whole in (None, 0):
        return None
    return round(100.0 * float(part) / float(whole), digits)


def derive(results: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Second-layer metrics. Every input number comes from a SQL report."""
    headline = one(results["c_headline_kpis"])
    counts = {row["table_name"]: row["row_count"] for row in results["a_row_counts"]}
    null_audit = one(results["p_null_audit"])

    payment = results["e_payment_method"]
    prepaid = [r for r in payment if r["payment_method"] in ("CARD", "UPI")]
    prepaid_orders = sum(r["orders"] for r in prepaid)
    prepaid_returns = sum(r["returned_orders"] for r in prepaid)
    prepaid_returned_net = sum(r["returned_net_gmv"] for r in prepaid)
    cod = next(r for r in payment if r["payment_method"] == "COD")

    returned = results["m_returned_orders"]
    top5 = returned[:5]
    top5_leak = sum(r["returned_net_gmv"] for r in top5)
    outliers = results["l_quantity_outliers"]
    outlier_returned_net = sum(r["net_gmv"] for r in outliers if r["returned"] == 1)
    outlier_net = sum(r["net_gmv"] for r in outliers)

    dupes = results["n_duplicate_fingerprints"]
    extra_duplicate_rows = sum(r["copy_count"] - 1 for r in dupes)

    realized_net = round(headline["net_gmv"] - headline["returned_net_gmv"], 2)

    rating_rows = results["j_rating_vs_return"]
    low_rating = [r for r in rating_rows if r["rating_bucket"] in ("1", "2")]
    high_rating = [r for r in rating_rows if r["rating_bucket"] in ("4", "5")]
    low_orders = sum(r["orders"] for r in low_rating)
    low_returns = sum(r["returned_orders"] for r in low_rating)
    high_orders = sum(r["orders"] for r in high_rating)
    high_returns = sum(r["returned_orders"] for r in high_rating)

    cities = results["g_city"]
    worst_city = max(cities, key=lambda r: r["returned_net_gmv"])
    highest_rate_city = max(cities, key=lambda r: (r["return_rate_pct"], r["orders"]))

    categories = results["d_category_margin_leakage"]
    worst_category = max(categories, key=lambda r: r["returned_net_gmv"])
    highest_rate_category = max(categories, key=lambda r: r["return_rate_pct"])

    products = results["i_product_leakage"]
    worst_product = products[0]
    discount = results["h_discount_band"]
    sources = results["k_acquisition_source"]
    worst_source = max(sources, key=lambda r: r["return_rate_pct"])
    tiers = results["f_city_tier"]

    before_signup = results["o_orders_before_signup"]

    return {
        "layer": "python_analysis",
        "inputs_from": "sql/analysis_reports.sql executed against mamaearth.db",
        "row_counts": counts,
        "headline": {
            **headline,
            "realized_net_gmv": realized_net,
        },
        "null_audit": null_audit,
        "payment": {
            "by_method": payment,
            "cod_return_rate_pct": cod["return_rate_pct"],
            "cod_returned_net_gmv": cod["returned_net_gmv"],
            "prepaid_orders": prepaid_orders,
            "prepaid_returned_orders": prepaid_returns,
            "prepaid_return_rate_pct": share(prepaid_returns, prepaid_orders),
            "prepaid_returned_net_gmv": round(prepaid_returned_net, 2),
            "cod_vs_prepaid_return_rate_pp": round(
                float(cod["return_rate_pct"]) - float(share(prepaid_returns, prepaid_orders) or 0),
                2,
            ),
        },
        "geography": {
            "city_tier": tiers,
            "cities": cities,
            "highest_leakage_city": worst_city,
            "highest_return_rate_city": highest_rate_city,
        },
        "category": {
            "rows": categories,
            "highest_leakage_category": worst_category,
            "highest_return_rate_category": highest_rate_category,
            "rating_by_category": results["b_rating_by_category"],
        },
        "product": {
            "rows": products,
            "highest_leakage_product": worst_product,
        },
        "discount_band": discount,
        "rating_vs_return": {
            "rows": rating_rows,
            "rating_1_2_orders": low_orders,
            "rating_1_2_return_rate_pct": share(low_returns, low_orders),
            "rating_4_5_orders": high_orders,
            "rating_4_5_return_rate_pct": share(high_returns, high_orders),
        },
        "acquisition": {
            "rows": sources,
            "highest_return_rate_source": worst_source,
        },
        "concentration": {
            "returned_order_count": len(returned),
            "top5_returned_orders": top5,
            "top5_returned_net_gmv": round(top5_leak, 2),
            "top5_share_of_returned_net_pct": share(top5_leak, headline["returned_net_gmv"]),
        },
        "data_quality": {
            "quantity_outliers": outliers,
            "outlier_net_gmv": round(outlier_net, 2),
            "outlier_returned_net_gmv": round(outlier_returned_net, 2),
            "outlier_share_of_returned_net_pct": share(outlier_returned_net, headline["returned_net_gmv"]),
            "duplicate_groups": dupes,
            "extra_duplicate_rows": extra_duplicate_rows,
            "orders_before_signup_count": len(before_signup),
            "orders_before_signup": before_signup,
        },
        "action_subset": {
            "definition": "Returned COD orders plus quantity outliers; the overlap where ops and finance should intervene first.",
            "highest_single_return_order_id": returned[0]["order_id"] if returned else None,
            "highest_single_return_net_gmv": returned[0]["returned_net_gmv"] if returned else None,
        },
    }


def run() -> dict[str, Any]:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        results = execute_reports(conn)
    metrics = derive(results)
    (OUTPUTS / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return metrics


if __name__ == "__main__":
    payload = run()
    h = payload["headline"]
    print(
        f"orders={h['orders']} returned={h['returned_orders']} "
        f"return_rate={h['return_rate_pct']}% returned_net={h['returned_net_gmv']}"
    )
