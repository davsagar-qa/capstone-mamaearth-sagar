from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
METRICS_PATH = OUTPUTS / "metrics.json"
BRIEF_PATH = OUTPUTS / "ops_finance_brief.md"

SYSTEM_RULES = """You are writing an action brief for Mamaearth regional ops and finance heads.
Use ONLY numbers present in the JSON facts. Do not invent, round into a new figure, or cite external benchmarks.
If a comparison is needed, use the pre-computed fields in the JSON.
Audience: busy regional ops + finance. Structure:

1. Verdict (2-3 sentences)
2. Where the rupees leak (geography, category, payment, SKUs)
3. What is noise vs signal (outliers, duplicates, orders before signup)
4. Three numbered actions with an owner (Ops or Finance) and the supporting number from the facts
5. What not to do based on this sample

Never introduce a number that is not in the facts JSON.
"""


def flatten_numbers(obj: Any, bag: set[str]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, int):
        bag.add(str(obj))
        bag.add(f"{obj:,}")
        return
    if isinstance(obj, float):
        bag.add(str(obj))
        if obj == int(obj):
            bag.add(str(int(obj)))
        bag.add(f"{obj:.0f}")
        bag.add(f"{obj:.1f}")
        bag.add(f"{obj:.2f}")
        return
    if isinstance(obj, dict):
        for v in obj.values():
            flatten_numbers(v, bag)
    elif isinstance(obj, list):
        for v in obj:
            flatten_numbers(v, bag)


def assert_grounded(text: str, metrics: dict[str, Any]) -> None:
    allowed = set()
    flatten_numbers(metrics, allowed)
    allowed.update({"-", "–"})
    found = re.findall(r"(?<![A-Za-z0-9])-?\d+(?:,\d{3})*(?:\.\d+)?(?![A-Za-z0-9])", text)
    stray = []
    for raw in found:
        if raw in allowed:
            continue
        compact = raw.replace(",", "")
        if compact in allowed:
            continue
        stray.append(raw)
    if stray:
        raise ValueError(f"Narrative used numbers not present in metrics.json: {sorted(set(stray))}")


def facts_for_prompt(metrics: dict[str, Any]) -> dict[str, Any]:
    """Compact facts for the model. All values copied from analysis output."""
    h = metrics["headline"]
    p = metrics["payment"]
    g = metrics["geography"]
    c = metrics["category"]
    dq = metrics["data_quality"]
    conc = metrics["concentration"]
    r = metrics["rating_vs_return"]
    a = metrics["acquisition"]
    return {
        "row_counts": metrics["row_counts"],
        "headline": h,
        "null_audit": metrics["null_audit"],
        "cod_return_rate_pct": p["cod_return_rate_pct"],
        "prepaid_return_rate_pct": p["prepaid_return_rate_pct"],
        "cod_vs_prepaid_return_rate_pp": p["cod_vs_prepaid_return_rate_pp"],
        "cod_returned_net_gmv": p["cod_returned_net_gmv"],
        "payment_by_method": p["by_method"],
        "city_tier": g["city_tier"],
        "highest_leakage_city": g["highest_leakage_city"],
        "highest_return_rate_city": g["highest_return_rate_city"],
        "cities": g["cities"],
        "highest_leakage_category": c["highest_leakage_category"],
        "highest_return_rate_category": c["highest_return_rate_category"],
        "categories": c["rows"],
        "rating_by_category": c["rating_by_category"],
        "highest_leakage_product": metrics["product"]["highest_leakage_product"],
        "top_products": metrics["product"]["rows"][:5],
        "discount_band": metrics["discount_band"],
        "rating_1_2_return_rate_pct": r["rating_1_2_return_rate_pct"],
        "rating_4_5_return_rate_pct": r["rating_4_5_return_rate_pct"],
        "rating_vs_return": r["rows"],
        "highest_return_rate_source": a["highest_return_rate_source"],
        "top5_share_of_returned_net_pct": conc["top5_share_of_returned_net_pct"],
        "top5_returned_orders": conc["top5_returned_orders"],
        "quantity_outliers": dq["quantity_outliers"],
        "outlier_returned_net_gmv": dq["outlier_returned_net_gmv"],
        "outlier_share_of_returned_net_pct": dq["outlier_share_of_returned_net_pct"],
        "extra_duplicate_rows": dq["extra_duplicate_rows"],
        "duplicate_groups": dq["duplicate_groups"],
        "orders_before_signup_count": dq["orders_before_signup_count"],
        "action_subset": metrics["action_subset"],
    }


def deterministic_brief(facts: dict[str, Any]) -> str:
    h = facts["headline"]
    city = facts["highest_leakage_city"]
    cat = facts["highest_leakage_category"]
    sku = facts["highest_leakage_product"]
    top = facts["top5_returned_orders"][0]
    outlier = facts["quantity_outliers"][0]
    returned_outlier = next(row for row in facts["quantity_outliers"] if row["returned"] == 1)
    source = facts["highest_return_rate_source"]
    rate_city = facts["highest_return_rate_city"]
    methods = {row["payment_method"]: row for row in facts["payment_by_method"]}
    tiers = {row["city_tier"]: row for row in facts["city_tier"]}
    return f"""# Mamaearth returns brief — regional ops & finance

*Every figure below is copied from `outputs/metrics.json`, which was computed from `sql/reports.sql` on `mamaearth.db`. No external numbers.*

## 1. Verdict

Returns are a real margin leak, not a rounding error. Of {h['orders']} orders, {h['returned_orders']} came back ({h['return_rate_pct']}% of orders) and reversed ₹{h['returned_net_gmv']} of discounted GMV — {h['returned_net_share_pct']}% of net GMV (₹{h['net_gmv']}). Realised net after reversing those returns is ₹{h['realized_net_gmv']}.

The leak is concentrated: the top 5 returned orders account for {facts['top5_share_of_returned_net_pct']}% of returned net GMV. Treat this as a subset problem (specific cities, COD, a few SKUs, and two quantity-outlier rows), not a brand-wide quality collapse.

## 2. Where the rupees leak

- **City:** {city['city']} (tier {city['city_tier']}) contributes ₹{city['returned_net_gmv']} of returned net on {city['returned_orders']} of {city['orders']} orders ({city['return_rate_pct']}% return rate). {rate_city['city']} has the highest city return rate at {rate_city['return_rate_pct']}% ({rate_city['returned_orders']} of {rate_city['orders']} orders).
- **City tier:** Tier 1 return rate is {tiers[1]['return_rate_pct']}% (₹{tiers[1]['returned_net_gmv']} leaked). Tier 2 is {tiers[2]['return_rate_pct']}% (₹{tiers[2]['returned_net_gmv']} leaked).
- **Category:** {cat['category']} is the largest rupee leak (₹{cat['returned_net_gmv']}, {cat['return_rate_pct']}% of {cat['orders']} orders). Highest category return *rate* is {facts['highest_return_rate_category']['category']} at {facts['highest_return_rate_category']['return_rate_pct']}%.
- **SKU:** {sku['product_name']} ({sku['product_id']}, {sku['category']}) leaked ₹{sku['returned_net_gmv']} across {sku['returned_orders']} of {sku['orders']} orders ({sku['return_rate_pct']}%).
- **Payment:** COD return rate is {facts['cod_return_rate_pct']}% vs prepaid {facts['prepaid_return_rate_pct']}% ({facts['cod_vs_prepaid_return_rate_pp']} pp higher). COD leaked ₹{facts['cod_returned_net_gmv']}. Card {methods['CARD']['return_rate_pct']}%, UPI {methods['UPI']['return_rate_pct']}%.
- **Experience:** Orders rated 1–2 return at {facts['rating_1_2_return_rate_pct']}%; orders rated 4–5 return at {facts['rating_4_5_return_rate_pct']}%.
- **Acquisition:** Highest return rate by source is {source['acquisition_source']} at {source['return_rate_pct']}% ({source['returned_orders']} of {source['orders']} orders).

Largest single reverse: {top['order_id']} — {top['customer_name']} in {top['city']}, {top['product_name']}, qty {top['quantity']}, {top['payment_method']}, ₹{top['returned_net_gmv']}.

## 3. Noise vs signal

- **Quantity outliers:** {outlier['order_id']} is qty {outlier['quantity']} (net ₹{outlier['net_gmv']}, returned={outlier['returned']}). Outlier returned net is ₹{facts['outlier_returned_net_gmv']} ({facts['outlier_share_of_returned_net_pct']}% of all returned net). Do not set a national return-rate target off these two rows.
- **Duplicate fingerprints:** {facts['extra_duplicate_rows']} extra rows share a customer/product/date/qty/payment fingerprint. Finance should strip them before board reporting.
- **Orders before signup:** {facts['orders_before_signup_count']} orders have `order_date` earlier than `signup_date` — a CRM/join issue, not a fulfilment issue.
- **Nulls (correctly stored as NULL, not empty strings):** {facts['null_audit']['null_discount_pct']} missing `discount_pct`, {facts['null_audit']['null_rating']} missing `rating`. Empty-string ratings: {facts['null_audit']['empty_string_rating']}. Rated orders in the headline: {h['rated_orders']}; average rating {h['avg_rating']}.

## 4. Actions

1. **Ops — Lucknow COD + Babycare outlier.** {top['order_id']} alone is ₹{top['returned_net_gmv']}. Freeze COD on qty>5 until a second review, and audit Lucknow reverse logistics. Supporting: Lucknow leaked ₹{city['returned_net_gmv']}; COD return rate {facts['cod_return_rate_pct']}%.
2. **Finance — restate net after returns and duplicates.** Publish realised net ₹{h['realized_net_gmv']} (net GMV ₹{h['net_gmv']} minus returned ₹{h['returned_net_gmv']}) and flag {facts['extra_duplicate_rows']} duplicate extra rows so margin packs are not inflated.
3. **Ops — SKU and prepaid mix.** Put {sku['product_name']} on a return watch (₹{sku['returned_net_gmv']} leaked, {sku['return_rate_pct']}% of its {sku['orders']} orders). Shift at-risk cities from COD toward UPI/Card where prepaid returns sit at {facts['prepaid_return_rate_pct']}%.

## 5. What not to do

Do not blame a single category for a company-wide quality failure: Babycare rupee leak is dominated by {returned_outlier['order_id']} (quantity {returned_outlier['quantity']}, ₹{returned_outlier['net_gmv']}). Do not treat missing ratings as zeros — {h['rated_orders']} of {h['orders']} orders have a rating. Do not set discount policy from this sample alone; use the discount-band table in `outputs/metrics.json` before cutting promo depth.
"""


def llm_brief(facts: dict[str, Any]) -> str | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from urllib import request

        payload = json.dumps(
            {
                "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": SYSTEM_RULES},
                    {
                        "role": "user",
                        "content": "Facts JSON:\n" + json.dumps(facts, ensure_ascii=False),
                    },
                ],
            }
        ).encode("utf-8")
        req = request.Request(
            os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions"),
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # noqa: BLE001 — fall back to grounded template
        print(f"LLM call failed ({exc}); using deterministic grounded brief.")
        return None


def run(metrics: dict[str, Any] | None = None) -> Path:
    if metrics is None:
        metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    facts = facts_for_prompt(metrics)
    text = llm_brief(facts) or deterministic_brief(facts)
    if not text.startswith("#"):
        text = "# Mamaearth returns brief — regional ops & finance\n\n" + text
    source = "openai" if os.environ.get("OPENAI_API_KEY") and "LLM call failed" not in text else "deterministic_template"
    header = (
        f"_Generator: {source}. Numbers grounded against `outputs/metrics.json`._\n\n"
    )
    if "Generator:" not in text:
        text = text.replace(
            "# Mamaearth returns brief — regional ops & finance",
            "# Mamaearth returns brief — regional ops & finance\n\n" + header,
            1,
        )
    assert_grounded(text, metrics)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    BRIEF_PATH.write_text(text.strip() + "\n", encoding="utf-8")
    return BRIEF_PATH


if __name__ == "__main__":
    path = run()
    print(f"Wrote {path}")
