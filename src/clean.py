"""Step 2: cleaning. Every decision is a small function and is logged.

Decisions (approved by the project author):
  1. Window: keep 2018-01-01 .. 2022-10-31 (months complete for everyone).
  2. Gift cards: FLAGGED (is_gift), not deleted. Base analysis uses ~is_gift;
     headline numbers are also shown with gift cards.
  3. Exact duplicates: FLAGGED (is_exact_dup), kept. No order ID, so a real
     repeat purchase cannot be told apart from a double-count.
  4. Missing category -> "Unknown". Rows are kept.
  5. No capping or trimming of prices or quantities.
Sensitive categories are merged into one bucket for category views only;
the rows stay in total spend and activity.
"""
import pathlib
import pandas as pd
from src.load import load_purchases, WINDOW_START, WINDOW_END

GIFT_CATEGORY_PATTERN = r"GIFT_(?:CARD|XXRD)"
GIFT_TITLE_PATTERN = "gift card"

SENSITIVE_CATEGORIES = {
    "MEDICATION", "OTC_MEDICATION", "INCONTINENCE_PROTECTOR",
    "DISPOSABLE_INCONTINENCE_SURFACE_PROTECTOR", "REUSABLE_INCONTINENCE_SURFACE_PROTECTOR",
    "MEDICAL_TEST_STRIP", "PERSONAL_PILL_DISPENSER", "PILL_CUTTER",
    "MEDICAL_COMPRESSION_GARMENT", "PROFESSIONAL_HEALTHCARE", "MEDICAL_SUPPLIES",
    "ABIS_DRUGSTORE", "SEXUAL_STIMULATION_DEVICE", "SEXUAL_WELLNESS", "BODY_LUBRICANT",
    "CONDOM", "BEER", "WINE", "RICE_WINE", "ALCOHOLIC_BEVERAGE",
    "ELECTRONIC_CIGARETTE_LIQUID", "CIGARETTE_CASE",
}
SENSITIVE_LABEL = "Sensitive (not broken out)"
UNKNOWN_LABEL = "Unknown"
DUP_KEY = ["order_date", "price", "qty", "state", "title", "asin", "category", "user_id"]


def apply_window(df, start=WINDOW_START, end=WINDOW_END):
    return df[df["date"].between(start, end)].copy()


def flag_gift_cards(df):
    by_cat = df["category"].str.contains(GIFT_CATEGORY_PATTERN, na=False)
    by_title = df["title"].str.contains(GIFT_TITLE_PATTERN, case=False, na=False)
    df = df.copy()
    df["is_gift"] = (by_cat | by_title).astype(bool)
    return df


def flag_duplicates(df):
    df = df.copy()
    df["is_exact_dup"] = df.duplicated(subset=DUP_KEY, keep="first").astype(bool)
    return df


def add_category_clean(df):
    df = df.copy()
    cat = df["category"].astype("object")
    out = cat.where(cat.notna(), UNKNOWN_LABEL)
    out = out.where(~out.isin(SENSITIVE_CATEGORIES), SENSITIVE_LABEL)
    df["category_clean"] = out
    return df


def add_month(df):
    df = df.copy()
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    return df


def clean(df):
    """Return (clean_df, log_df). Only the window step deletes rows."""
    n0, s0 = len(df), df["spend"].sum()
    log = [{"step": "raw", "rows": n0, "rows_affected": 0, "spend_affected": 0.0,
            "rows_pct": 0.0, "spend_pct": 0.0, "action": "-"}]

    def add(step, rows, spend, action):
        log.append({"step": step, "rows": len(out), "rows_affected": int(rows),
                    "spend_affected": round(float(spend), 2),
                    "rows_pct": round(rows / n0 * 100, 2),
                    "spend_pct": round(spend / s0 * 100, 2), "action": action})

    out = apply_window(df)
    add("window 2018-01-01..2022-10-31", n0 - len(out), s0 - out["spend"].sum(), "removed")
    out = flag_gift_cards(out)
    add("gift cards", out["is_gift"].sum(), out.loc[out["is_gift"], "spend"].sum(),
        "flagged (excluded from base numbers)")
    out = flag_duplicates(out)
    add("exact duplicates", out["is_exact_dup"].sum(),
        out.loc[out["is_exact_dup"], "spend"].sum(), "flagged, kept")
    out = add_category_clean(out)
    add("missing category -> Unknown", (out["category_clean"] == UNKNOWN_LABEL).sum(),
        out.loc[out["category_clean"] == UNKNOWN_LABEL, "spend"].sum(), "relabelled, kept")
    add("sensitive categories merged", (out["category_clean"] == SENSITIVE_LABEL).sum(),
        out.loc[out["category_clean"] == SENSITIVE_LABEL, "spend"].sum(),
        "relabelled for category views, kept in totals")
    out = add_month(out)
    return out, pd.DataFrame(log)


def main():
    import duckdb
    out_dir = pathlib.Path("data/processed")
    out_dir.mkdir(parents=True, exist_ok=True)
    pathlib.Path("reports").mkdir(exist_ok=True)
    df, log = clean(load_purchases())
    log.to_csv("reports/cleaning_log.csv", index=False)
    keep = ["user_id", "date", "month", "price", "qty", "spend", "state", "title", "asin",
            "category", "category_clean", "is_gift", "is_exact_dup"]
    clean_df = df[keep]  # noqa: F841  (read by DuckDB below)
    duckdb.sql("COPY (SELECT * FROM clean_df) TO 'data/processed/purchases_clean.parquet' "
               "(FORMAT PARQUET)")
    print(log.to_string(index=False))
    base = df[~df["is_gift"]]
    print("\nbase table (window, gift cards excluded): rows", len(base),
          "| users", base["user_id"].nunique(), "| spend", round(base["spend"].sum()))
    print("saved data/processed/purchases_clean.parquet and reports/cleaning_log.csv")


if __name__ == "__main__":
    main()
