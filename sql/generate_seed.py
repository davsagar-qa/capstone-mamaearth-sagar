"""Generate sql/seed_data.sql from the CSVs. Blank discount_pct/rating become SQL NULL."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SQL = ROOT / "sql"


def sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sql_int(value: str) -> str:
    value = value.strip()
    if value == "":
        return "NULL"
    return str(int(value))


def main() -> None:
    lines = [
        "-- Auto-generated from data/*.csv. Re-run: python sql/generate_seed.py",
        "-- Blank discount_pct and rating cells are inserted as NULL, not empty strings.",
        "",
        "PRAGMA foreign_keys = ON;",
        "",
        "DELETE FROM orders;",
        "DELETE FROM products;",
        "DELETE FROM customers;",
        "",
    ]

    with (DATA / "customers.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lines.append(
                "INSERT INTO customers (customer_id, name, city, city_tier, signup_date, acquisition_source) VALUES ("
                f"{sql_str(row['customer_id'])}, {sql_str(row['name'])}, {sql_str(row['city'])}, "
                f"{int(row['city_tier'])}, {sql_str(row['signup_date'])}, {sql_str(row['acquisition_source'])});"
            )

    lines.append("")
    with (DATA / "products.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lines.append(
                "INSERT INTO products (product_id, product_name, category, price) VALUES ("
                f"{sql_str(row['product_id'])}, {sql_str(row['product_name'])}, "
                f"{sql_str(row['category'])}, {float(row['price']):.2f});"
            )

    lines.append("")
    with (DATA / "orders.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lines.append(
                "INSERT INTO orders (order_id, customer_id, product_id, order_date, quantity, discount_pct, payment_method, rating, returned) VALUES ("
                f"{sql_str(row['order_id'])}, {sql_str(row['customer_id'])}, {sql_str(row['product_id'])}, "
                f"{sql_str(row['order_date'])}, {int(row['quantity'])}, {sql_int(row['discount_pct'])}, "
                f"{sql_str(row['payment_method'])}, {sql_int(row['rating'])}, {int(row['returned'])});"
            )

    lines.append("")
    out = SQL / "seed_data.sql"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
