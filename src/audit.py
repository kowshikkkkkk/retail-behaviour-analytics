"""Step 1: data audit. Measures problems; removes nothing. Prints aggregates only."""
import pathlib
import pandas as pd

RAW = pathlib.Path("data/raw")
OUT = pathlib.Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)

def h(t):
    print("\n=== " + t + " ===")

df = pd.read_csv(
    RAW / "amazon-purchases.csv", encoding="utf-8",
    dtype={"Shipping Address State": "string", "Title": "string",
           "ASIN/ISBN (Product Code)": "string", "Category": "string",
           "Survey ResponseID": "string"})
df.columns = ["order_date", "price", "qty", "state", "title", "asin", "category", "user_id"]
df["date"] = pd.to_datetime(df["order_date"], format="%Y-%m-%d", errors="coerce")
df["spend"] = df["price"] * df["qty"]

h("1. Size and dates")
print("rows:", len(df), "| users:", df.user_id.nunique())
print("unparseable dates:", int(df.date.isna().sum() - df.order_date.isna().sum()))
print("date range:", df.date.min().date(), "to", df.date.max().date())

h("2. Missing values (count, %)")
miss = df.drop(columns=["date", "spend"]).isna().sum()
print(pd.DataFrame({"missing": miss, "pct": (miss / len(df) * 100).round(2)}))

h("3. Users vs survey")
sv_cols = pd.read_csv(RAW / "survey.csv", nrows=0).columns
key = [c for c in sv_cols if "responseid" in c.lower()][0]
sv_ids = set(pd.read_csv(RAW / "survey.csv", usecols=[key])[key].dropna())
pu = set(df.user_id.dropna())
print("survey respondents:", len(sv_ids), "| purchasing users:", len(pu),
      "| in both:", len(sv_ids & pu))
per_user = df.groupby("user_id").size()
print("purchases per user:", per_user.describe().round(1).to_dict())
print("users with < 5 purchases:", int((per_user < 5).sum()))

h("4. Exact duplicate rows (may be legit repeat buys)")
dup = df.duplicated(keep="first")
print("duplicate rows:", int(dup.sum()), "| % of rows:", round(dup.mean() * 100, 2),
      "| % of spend:", round(df.loc[dup, "spend"].sum() / df.spend.sum() * 100, 2))

h("5. Price and quantity")
print(df.price.describe(percentiles=[.01, .5, .99, .999]).round(2).to_dict())
print("price == 0:", int((df.price == 0).sum()), "| price < 0:", int((df.price < 0).sum()),
      "| price > 1000:", int((df.price > 1000).sum()))
print("qty value counts (top):", df.qty.value_counts().head(8).to_dict())
print("non-integer qty:", int((df.qty % 1 != 0).sum()), "| qty > 10:", int((df.qty > 10).sum()),
      "| qty <= 0:", int((df.qty <= 0).sum()))
print("total spend:", round(df.spend.sum(), 2),
      "| share of spend from top 0.1% of rows:",
      round(df.spend.nlargest(int(len(df) * 0.001)).sum() / df.spend.sum() * 100, 1), "%")

h("6. Gift cards")
gift = (df.category.str.contains("GIFT_CARD", na=False)
        | df.title.str.contains("gift card", case=False, na=False))
print("gift-card rows:", int(gift.sum()), "| % of rows:", round(gift.mean() * 100, 2),
      "| % of spend:", round(df.loc[gift, "spend"].sum() / df.spend.sum() * 100, 2))
tot = df.groupby("user_id").spend.sum()
gsp = df[gift].groupby("user_id").spend.sum().reindex(tot.index).fillna(0)
print("users with > 50% of spend on gift cards:", int((gsp / tot > 0.5).sum()))
print("categories matching 'GIFT':", sorted(df.category[df.category.str.contains("GIFT", na=False)].unique())[:10])

h("7. Shipping state")
st = df.state.dropna()
print("unique values:", st.nunique(), "| values not 2 letters:", int((st.str.len() != 2).sum()))

h("8. Rows per year, and the tail (is the end of the data complete?)")
y = df.groupby(df.date.dt.year).agg(rows=("price", "size"), users=("user_id", "nunique"),
                                    spend=("spend", "sum")).round(0)
print(y)
m = df.groupby(df.date.dt.to_period("M")).size()
print("last 12 months of rows:\n", m.tail(12))

h("9. Categories")
cat = (df.groupby("category", dropna=False)
         .agg(rows=("price", "size"), spend=("spend", "sum"))
         .sort_values("rows", ascending=False))
cat.to_csv(OUT / "category_counts.csv")
print("unique categories:", len(cat), "| top 15 share of rows:",
      round(cat.rows.head(15).sum() / len(df) * 100, 1), "%")
print("saved full list to data/processed/category_counts.csv (git-ignored)")
