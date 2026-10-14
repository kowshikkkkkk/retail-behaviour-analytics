"""Step 4: monetization. Descriptive only. Confidence intervals come in the inference step."""
import math
import pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from src.sql_metrics import SQL_DIR, connect, run

TOP_N = 15
MIN_ACCOUNTS = 30


def run_category_mix(con, top_n=TOP_N, min_accounts=MIN_ACCOUNTS):
    sql = (SQL_DIR / "06_category_mix.sql").read_text()
    sql = sql.replace("__TOP_N__", str(top_n)).replace("__MIN_ACCOUNTS__", str(min_accounts))
    return con.execute(sql).df()


def gini(x):
    """0 = everyone spends the same, close to 1 = one account spends nearly everything."""
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    return float(2 * np.sum(np.arange(1, n + 1) * x) / (n * x.sum()) - (n + 1) / n)


def top_share(x, frac):
    x = np.sort(np.asarray(x, dtype=float))[::-1]
    k = math.ceil(frac * len(x) - 1e-9)
    return float(x[:k].sum() / x.sum())


def share_of_accounts_for_half(x):
    x = np.sort(np.asarray(x, dtype=float))[::-1]
    k = int(np.searchsorted(np.cumsum(x), 0.5 * x.sum() - 1e-9) + 1)
    return k / len(x)


def concentration(x):
    x = np.asarray(x, dtype=float)
    q = np.percentile(x, [10, 25, 50, 75, 90, 99])
    return {"accounts": len(x), "total_spend": float(x.sum()), "mean": float(x.mean()),
            "p10": q[0], "p25": q[1], "median": q[2], "p75": q[3], "p90": q[4], "p99": q[5],
            "max": float(x.max()), "top_1pct_share": top_share(x, 0.01),
            "top_10pct_share": top_share(x, 0.10), "gini": gini(x),
            "share_of_accounts_for_half_of_spend": share_of_accounts_for_half(x)}


def main():
    tables, figs = pathlib.Path("reports/tables"), pathlib.Path("reports/figures")
    tables.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)
    con = connect()
    spend = run(con, "02_user_metrics.sql")["spend"].to_numpy()
    full = concentration(spend)
    without_top = concentration(np.sort(spend)[:-1])
    conc = pd.DataFrame({"all_accounts": full, "without_largest_account": without_top})
    conc.to_csv(tables / "spend_concentration.csv")
    print("spend per account and concentration (point estimates; CIs come later):")
    print(conc.round(3).to_string())
    print("\nlargest account share of total spend:", round(spend.max() / spend.sum() * 100, 2), "%")

    cat = run_category_mix(con)
    cat.to_csv(tables / "category_mix.csv", index=False)
    print("\ncategory mix (share of spend):")
    print(cat.assign(spend=lambda d: d["spend"].round(0), share_of_spend=lambda d: d["share_of_spend"].round(4))
          .to_string(index=False))

    yr = run(con, "07_spend_by_year.sql")
    yr.to_csv(tables / "spend_by_year_jan_oct.csv", index=False)
    print("\nJan-Oct spend by year (same months each year, current dollars, not inflation-adjusted):")
    print(yr.round(1).to_string(index=False))

    x = np.sort(spend)
    cum = np.insert(np.cumsum(x) / x.sum(), 0, 0)
    pop = np.linspace(0, 1, len(cum))
    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    ax.plot(pop, cum, color="#1f5fa8", lw=2, label=f"Actual (Gini {full['gini']:.2f})")
    ax.plot([0, 1], [0, 1], color="grey", ls="--", lw=1, label="Everyone spends the same")
    ax.set_xlabel("Cumulative share of accounts (lowest to highest spend)")
    ax.set_ylabel("Cumulative share of total spend")
    ax.set_title(f"Top 10% of accounts = {full['top_10pct_share']:.0%} of spend\n(observational; volunteer sample)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(figs / "spend_concentration.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5.5))
    c = cat.iloc[::-1]
    ax.barh(c["category_group"], c["share_of_spend"] * 100, color="#c4501f")
    ax.set_xlabel("Share of spend (%)")
    ax.set_title("Where spend goes (gift cards excluded; Amazon product types)")
    fig.tight_layout()
    fig.savefig(figs / "category_mix.png", dpi=150)
    plt.close(fig)
    print("\nsaved tables and charts")


if __name__ == "__main__":
    main()
