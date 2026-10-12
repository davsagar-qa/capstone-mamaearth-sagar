"""Draw the two charts in visualizations/ from narrator/findings.json."""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

ROOT = Path(__file__).resolve().parents[1]
FINDINGS_PATH = ROOT / "narrator" / "findings.json"
OUTPUT_DIR = ROOT / "visualizations"
PAYMENT_COLORS = {"UPI": "#1B7F5A", "COD": "#E07A3D", "CARD": "#2F5D8C"}


def load_findings():
    if not FINDINGS_PATH.exists():
        raise SystemExit(
            "narrator/findings.json was not found. Run analysis/clean_and_eda.py before this script."
        )
    findings = json.loads(FINDINGS_PATH.read_text(encoding="utf-8"))
    if "chart_return_rate_by_payment" not in findings or "chart_monthly_revenue" not in findings:
        raise SystemExit(
            "findings.json has no chart series. Run analysis/clean_and_eda.py before this script."
        )
    return findings


def style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors="#333333")


def draw_return_rate(findings):
    rows = findings["chart_return_rate_by_payment"]
    if not rows:
        raise SystemExit("findings.json has no chart_return_rate_by_payment rows.")

    labels = [row["payment_method"] for row in rows]
    rates = [row["return_rate_pct"] for row in rows]
    colors = [PAYMENT_COLORS.get(label, "#6B7280") for label in labels]
    cod = next(row["return_rate_pct"] for row in rows if row["payment_method"] == "COD")
    card = next(row["return_rate_pct"] for row in rows if row["payment_method"] == "CARD")
    multiple = round(cod / card)

    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    bars = ax.bar(labels, rates, color=colors, width=0.62)
    style_axes(ax)
    ax.set_title(
        f"COD Returns at {cod:.1f}% — {multiple}x Card",
        loc="left",
        fontsize=14,
        color="#1F2933",
        pad=12,
    )
    ax.set_ylabel("Return rate (%)")
    ax.set_xlabel("Payment method")
    highest = max(rates) if rates else 0
    ax.set_ylim(0, max(highest * 1.22, 10))

    for bar, rate in zip(bars, rates):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + highest * 0.03,
            f"{rate:.1f}%",
            ha="center",
            va="bottom",
            fontsize=11,
            color="#1F2933",
        )

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "return_rate_by_payment.png", dpi=160)
    plt.close(fig)


def draw_monthly_revenue(findings):
    rows = findings["chart_monthly_revenue"]
    if not rows:
        raise SystemExit("findings.json has no chart_monthly_revenue rows.")

    labels = [row["order_month"] for row in rows]
    revenue = [row["order_value"] for row in rows]
    peak = max(rows, key=lambda row: row["order_value"])
    peak_label = {
        "01": "January",
        "02": "February",
        "03": "March",
        "04": "April",
        "05": "May",
        "06": "June",
        "07": "July",
        "08": "August",
        "09": "September",
        "10": "October",
        "11": "November",
        "12": "December",
    }[peak["order_month"].split("-")[1]]
    peak_year = peak["order_month"].split("-")[0]

    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    ax.plot(labels, revenue, color="#1B7F5A", marker="o", linewidth=2.2, markersize=7)
    ax.fill_between(labels, revenue, color="#1B7F5A", alpha=0.12)
    style_axes(ax)
    ax.set_title(
        f"{peak_label} {peak_year} Is the Peak Month Once Bulk Orders Are Excluded",
        loc="left",
        fontsize=13,
        color="#1F2933",
        pad=12,
    )
    ax.set_ylabel("Order value (INR)")
    ax.set_xlabel("Order month")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda value, _pos: f"{value:,.0f}"))

    peak_value = max(revenue) if revenue else 0
    ax.set_ylim(0, peak_value * 1.18 if peak_value else 1)
    for label, value in zip(labels, revenue):
        ax.text(label, value + peak_value * 0.03, f"{value:,.0f}", ha="center", va="bottom", fontsize=8, color="#1F2933")

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "monthly_revenue_trend.png", dpi=160)
    plt.close(fig)


def main():
    findings = load_findings()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    draw_return_rate(findings)
    draw_monthly_revenue(findings)
    print(f"Wrote {OUTPUT_DIR / 'return_rate_by_payment.png'}")
    print(f"Wrote {OUTPUT_DIR / 'monthly_revenue_trend.png'}")


if __name__ == "__main__":
    sys.exit(main())
