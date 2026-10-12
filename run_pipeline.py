from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.analyze import run as run_analysis
from narrative.generate_brief import run as run_narrative
from sql.generate_seed import main as generate_seed

SQL_DIR = ROOT / "sql"
DB_PATH = ROOT / "mamaearth.db"


def build_database() -> None:
    generate_seed()
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))
        conn.executescript((SQL_DIR / "seed_data.sql").read_text(encoding="utf-8"))
        conn.commit()
        cur = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM customers) AS customers,
                (SELECT COUNT(*) FROM products) AS products,
                (SELECT COUNT(*) FROM orders) AS orders,
                (SELECT COUNT(*) FROM orders WHERE rating IS NULL) AS null_ratings,
                (SELECT COUNT(*) FROM orders WHERE typeof(rating) = 'text' AND rating = '') AS empty_string_ratings
            """
        )
        row = cur.fetchone()
        print(
            f"Loaded customers={row[0]} products={row[1]} orders={row[2]} "
            f"null_ratings={row[3]} empty_string_ratings={row[4]}"
        )
        if row[0] != 45 or row[1] != 16 or row[2] != 180:
            raise SystemExit("Seed counts do not match required 45 / 16 / 180.")
        if row[4] != 0:
            raise SystemExit("rating still contains empty strings; Report (b) would be wrong.")
    finally:
        conn.close()


def main() -> None:
    build_database()
    metrics = run_analysis()
    brief = run_narrative(metrics)
    print(f"Analysis -> {ROOT / 'outputs' / 'metrics.json'}")
    print(f"Narrative -> {brief}")


if __name__ == "__main__":
    main()
