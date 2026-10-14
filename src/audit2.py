"""Step 1b: what would each cleaning choice change? Removes nothing."""
import pandas as pd
from src.load import load_purchases, WINDOW_START, WINDOW_END

df = load_purchases()
base_rows, base_spend = len(df), df.spend.sum()

print("=== Gift-card categories (all) ===")
print(df[df.category.str.contains("GIFT|XXRD", na=False)]
      .groupby("category").size().sort_values(ascending=False).to_string())

gift_cat = df.category.str.contains(r"GIFT_(?:CARD|XXRD)", na=False)
gift_title = df.title.str.contains("gift card", case=False, na=False)
gift = gift_cat | gift_title
only_title = gift_title & ~gift_cat
print("\ngift rows by category:", int(gift_cat.sum()), "| by title only:", int(only_title.sum()),
      "| total:", int(gift.sum()), "| % of spend:", round(df.loc[gift, "spend"].sum() / base_spend * 100, 2))
print("top titles matched by title only (check for false positives):")
print(df.loc[only_title, "title"].str[:60].value_counts().head(10).to_string())

print("\n=== Penny prices ===")
print("price < 0.10:", int((df.price < 0.10).sum()), "| price < 0.50:", int((df.price < 0.50).sum()))

in_win = df.date.between(WINDOW_START, WINDOW_END)
key = ["order_date", "price", "qty", "state", "title", "asin", "category", "user_id"]

def row(name, d):
    u = d.groupby("user_id").spend.sum()
    return {"version": name, "rows": len(d),
            "rows_removed_pct": round((1 - len(d) / base_rows) * 100, 2),
            "spend": round(d.spend.sum()),
            "spend_removed_pct": round((1 - d.spend.sum() / base_spend) * 100, 2),
            "users": d.user_id.nunique(),
            "median_spend_per_user": round(u.median()),
            "mean_spend_per_user": round(u.mean())}

w = df[in_win]
wg = w[~gift[in_win]]
wgd = wg.drop_duplicates(subset=key)
wd = w.drop_duplicates(subset=key)
print("\n=== Impact of each choice (cumulative unless noted) ===")
print(pd.DataFrame([row("0 raw", df),
                    row("1 window only", w),
                    row("2 window, no gift cards", wg),
                    row("3 = 2 + dedup", wgd),
                    row("side: window + dedup, gift cards kept", wd)]).to_string(index=False))
print("rows after window end:", int((df.date > WINDOW_END).sum()),
      "| rows before window start:", int((df.date < WINDOW_START).sum()))

print("\n=== Sensitive-category candidates (rows) - for YOUR approval ===")
pat = ("CONDOM|CONTRACEP|LUBRICANT|PREGNANCY|SEXUAL|ADULT|VIBRAT|MEDICATION|DRUG|TOBACCO|"
       "CIGAR|VAPE|ALCOHOL|WINE|BEER|LIQUOR|CANNABIS|HEMP|CBD|MEDICAL|DIABET|INCONTINENCE|"
       "SUPPLEMENT|PILL|TEST_KIT|HEALTH")
sens = df[df.category.str.contains(pat, na=False)].groupby("category").size().sort_values(ascending=False)
print("matching categories:", len(sens), "| rows:", int(sens.sum()),
      "| % of rows:", round(sens.sum() / base_rows * 100, 2))
print(sens.head(40).to_string())
