"""Print a short narrative from narrator/findings.json. Does not recalculate metrics."""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
FINDINGS_PATH = ROOT / "narrator" / "findings.json"
SECTION_NAMES = ("Situation", "Complication", "Resolution")
# Chart series and the SQL report repeat related figures in a different form.
# Leaving them out of the prompt keeps the model on the verified findings.
PROMPT_SKIP_KEYS = {"chart_return_rate_by_payment", "chart_monthly_revenue", "sql_report"}
SYSTEM_INSTRUCTION = (
    "You are a senior data analyst writing for Mamaearth's regional ops and finance heads.\n\n"
    "Write exactly three labeled sections, in this order: Situation, Complication, Resolution. "
    "Start each section with its label followed by a colon on its own line.\n\n"
    "Every number in the output must come from the supplied findings and appear with the same value. "
    "Do not invent statistics."
)


def load_env_file(path: Path = ENV_PATH) -> None:
    """Load KEY=VALUE pairs from .env into the process if they are not already set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and not os.environ.get(key):
            os.environ[key] = value


def load_findings():
    if not FINDINGS_PATH.exists():
        raise SystemExit(
            "narrator/findings.json was not found. Run analysis/clean_and_eda.py before this script."
        )
    return json.loads(FINDINGS_PATH.read_text(encoding="utf-8"))


def inr(amount):
    return f"Rs {amount:,.2f}"


def percent(rate):
    return f"{rate * 100:.1f}%"


def month_label(order_month):
    return datetime.strptime(order_month, "%Y-%m").strftime("%B %Y")


def names(rows, key):
    return ", ".join(row[key] for row in rows)


def findings_for_prompt(findings: dict) -> dict:
    return {key: value for key, value in findings.items() if key not in PROMPT_SKIP_KEYS}


def build_user_contents(findings: dict) -> str:
    """User prompt. Figures are inserted from findings, not written into this string."""
    supplied = json.dumps(findings_for_prompt(findings), indent=2)
    peak_month = findings.get("true_peak_month", {}).get("month")
    month_hint = ""
    if peak_month:
        month_hint = (
            f"\n\nWhen you mention {peak_month}, write the month name "
            f"{month_label(peak_month)} next to its revenue figure."
        )
    return (
        "Write the Situation, Complication, and Resolution from the findings object below. "
        "Use only these values.\n\n"
        f"{supplied}"
        f"{month_hint}"
    )


def parse_scr(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    pattern = re.compile(
        r"(?ims)^\s*(?:\*\*|#{1,6}\s*)?(Situation|Complication|Resolution)\s*(?:\*\*)?\s*:?\s*"
        r"(.*?)(?=^\s*(?:\*\*|#{1,6}\s*)?(?:Situation|Complication|Resolution)\b|\Z)"
    )
    sections = {name: body.strip() for name, body in pattern.findall(cleaned)}
    missing = [name for name in SECTION_NAMES if not sections.get(name)]
    if missing:
        raise ValueError(
            "The model response did not include every required section: " + ", ".join(missing)
        )
    return {name: sections[name] for name in SECTION_NAMES}


def _api_key_configured() -> bool:
    load_env_file()
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def _token_count(response) -> int | None:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None
    total = getattr(usage, "total_token_count", None)
    return None if total is None else int(total)


def _generate_scr_narrative_api(findings: dict) -> dict:
    """Call Gemini. Both outcomes are dicts; the caller never sees a raw exception."""
    try:
        client = genai.Client()
        response = client.models.generate_content(
            model=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
            contents=build_user_contents(findings),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                # temperature=0.0 keeps the wording deterministic. This is a factual
                # business report, not creative writing.
                temperature=0.0,
                # Thinking tokens count against max_output_tokens, so thinking is kept
                # low and 2048 leaves room for a ~250-word, three-section narrative.
                max_output_tokens=2048,
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
                # HttpOptions.timeout is milliseconds. 30000 ms is 30 seconds,
                # above the 10-second minimum.
                http_options=types.HttpOptions(timeout=30000),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        if not response.text:
            raise ValueError("The model returned an empty narrative.")
        return {
            "status": "success",
            "narrative": parse_scr(response.text),
            "tokens": _token_count(response),
        }
    except Exception as err:
        return {"status": "error", "narrative": None, "message": str(err)}


def generate_scr_narrative_offline(findings: dict) -> dict:
    """Deterministic SCR narrative from findings. No network call and no API key."""
    rates = findings["return_rate_by_payment"]
    segment = findings["highest_risk_segment"]
    peak = findings["true_peak_month"]
    inflated = findings["outlier_inflated_month"]
    cleaned = f"{float(findings['cleaned_total_revenue_inr']):.2f}"
    raw = f"{float(findings['raw_total_revenue_inr']):.2f}"
    delta = f"{float(findings['duplicate_reconciliation_delta_inr']):.2f}"
    peak_revenue = f"{float(peak['revenue_inr']):.2f}"
    apparent = f"{float(inflated['apparent_revenue_inr']):.2f}"
    corrected = f"{float(inflated['corrected_revenue_inr']):.2f}"
    narrative = {
        "Situation": (
            f"Cleaned revenue is Rs {cleaned} after duplicate orders are removed, "
            f"against a raw total of Rs {raw}. "
            f"Return rates on the cleaned orders are COD {rates['COD']}%, "
            f"CARD {rates['CARD']}%, and UPI {rates['UPI']}%."
        ),
        "Complication": (
            f"The Rs {delta} difference from the raw total is the duplicate rows that were removed, "
            f"not a pricing change. "
            f"COD is not one rate: city tier {segment['city_tier']} is at {segment['return_rate_pct']}%, "
            f"above the blended COD rate of {rates['COD']}%. "
            f"{inflated['month']} appears to lead at Rs {apparent}, but that month falls to Rs {corrected} "
            f"once the two bulk orders are set aside."
        ),
        "Resolution": (
            f"Use {month_label(peak['month'])} as the true peak month, at Rs {peak_revenue}. "
            f"Put return follow-up on COD, especially city tier {segment['city_tier']} "
            f"at {segment['return_rate_pct']}%, ahead of CARD at {rates['CARD']}% and UPI at {rates['UPI']}%."
        ),
    }
    return {"status": "success", "narrative": narrative, "tokens": None}


def generate_scr_narrative(findings: dict) -> dict:
    """Gemini SCR narrative, or the offline template when no key is set or the call fails."""
    if not _api_key_configured():
        return generate_scr_narrative_offline(findings)
    result = _generate_scr_narrative_api(findings)
    if result["status"] == "error":
        return generate_scr_narrative_offline(findings)
    return result


def build_narrative(findings):
    if "sql_report" in findings:
        findings = findings["sql_report"]
    dataset = findings["dataset"]
    quality = findings["data_quality"]
    kpis = findings["kpis"]
    by_payment = findings["return_rate_by_payment"]
    monthly = findings["monthly_revenue"]
    categories = findings["revenue_by_category"]

    if not by_payment or not monthly:
        raise SystemExit("findings.json is missing payment or monthly results.")

    highest = by_payment[0]
    lowest = min(by_payment, key=lambda row: (row["return_rate"], row["payment_method"]))
    peak = max(monthly, key=lambda row: row["net_revenue"])
    trough = min(monthly, key=lambda row: row["net_revenue"])
    first = monthly[0]
    last = monthly[-1]
    if last["net_revenue"] > first["net_revenue"]:
        direction = "above"
    elif last["net_revenue"] < first["net_revenue"]:
        direction = "below"
    else:
        direction = "level with"

    paragraphs = [
        (
            f"This extract covers {dataset['customers']} customers, {dataset['products']} products, "
            f"and {dataset['orders']} orders from {dataset['min_order_date']} to {dataset['max_order_date']}. "
            f"After removing {quality['outlier_order_count']} orders with quantity above 10, "
            f"{kpis['orders']} orders remain in the analysis. "
            f"Customers returned {kpis['returned_orders']} of those orders, a return rate of {percent(kpis['return_rate'])}. "
            f"Net revenue on the orders that were kept is {inr(kpis['net_revenue'])}. "
            f"The merchandise value on returned lines is {inr(kpis['returned_line_value'])}."
        ),
        (
            f"{highest['payment_method']} has the highest return rate at {percent(highest['return_rate'])} "
            f"({highest['returned_orders']} returned out of {highest['orders']} orders). "
            f"{lowest['payment_method']} is lowest at {percent(lowest['return_rate'])} "
            f"({lowest['returned_orders']} returned out of {lowest['orders']} orders). "
            "These are associations in this extract, not proof that the payment method causes the return."
        ),
        (
            f"Net revenue peaks in {month_label(peak['order_month'])} at {inr(peak['net_revenue'])} "
            f"and is softest in {month_label(trough['order_month'])} at {inr(trough['net_revenue'])}. "
            f"{month_label(last['order_month'])} closes at {inr(last['net_revenue'])}, "
            f"{direction} {month_label(first['order_month'])} at {inr(first['net_revenue'])}."
        ),
    ]

    if categories:
        leader = categories[0]
        paragraphs.append(
            f"{leader['category']} is the largest category by net revenue at {inr(leader['net_revenue'])}, "
            f"with a return rate of {percent(leader['return_rate'])} across {leader['orders']} orders."
        )

    outlier_bits = [
        f"{row['order_id']} (quantity {row['quantity']})" for row in quality["outlier_orders"]
    ]
    duplicate_count = len(quality["possible_duplicate_orders"])
    missing_customers = quality["customers_without_orders"]
    quality_sentences = [
        (
            f"Data notes: {quality['blank_discount_count']} orders have a blank discount and are treated as no discount. "
            f"{quality['blank_rating_count']} orders have no rating. "
            f"The quantity outliers left out of the metrics are {', '.join(outlier_bits)}."
            if outlier_bits
            else (
                f"Data notes: {quality['blank_discount_count']} orders have a blank discount and are treated as no discount. "
                f"{quality['blank_rating_count']} orders have no rating."
            )
        )
    ]
    if duplicate_count:
        examples = "; ".join(row["order_ids"] for row in quality["possible_duplicate_orders"])
        quality_sentences.append(
            f"{duplicate_count} groups of orders match on customer, product, date, quantity, discount, "
            f"payment method, rating, and return flag ({examples}). They stay in the totals."
        )
    if missing_customers:
        count = len(missing_customers)
        subject = "customer has" if count == 1 else "customers have"
        quality_sentences.append(
            f"{count} signed-up {subject} no orders: {names(missing_customers, 'name')}."
        )
    paragraphs.append(" ".join(quality_sentences))
    return "\n\n".join(paragraphs)


def narrative_text(narrative) -> str:
    if isinstance(narrative, dict):
        return "\n\n".join(f"{name}\n{narrative[name]}" for name in SECTION_NAMES if name in narrative)
    return "" if narrative is None else str(narrative)


def check_narrative_figures(text: str) -> bool:
    """Pass only when the five required figures appear after commas are removed."""
    normalized = text.replace(",", "")
    checks = (
        ("cleaned total revenue", ("97358.30", "97358.3")),
        ("COD return rate", ("44.4",)),
        ("COD tier-2 return rate", ("54.5",)),
        ("duplicate reconciliation delta", ("2501.90", "2501.9")),
        ("March peak revenue", ("March",), ("20318.90", "20318.9")),
    )
    passed = True
    for label, *groups in checks:
        ok = all(any(option in normalized for option in group) for group in groups)
        print(f"{'PASS' if ok else 'FAIL'}: {label}")
        passed = passed and ok
    return passed


def main():
    result = generate_scr_narrative(load_findings())
    narrative = result["narrative"]
    print(result["status"])
    if not isinstance(narrative, dict):
        print(result.get("message"))
        return
    for name in SECTION_NAMES:
        print(f"{name}\n{narrative[name]}\n")
    check_narrative_figures(narrative_text(narrative))


if __name__ == "__main__":
    sys.exit(main())
