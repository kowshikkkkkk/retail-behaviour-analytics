"""Step 3: activity over time. Observational; not retention or churn (see README)."""
import pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from src.sql_metrics import SQL_DIR, connect, run

GAPS = (2, 3, 4)
DEFAULT_GAP = 3


def run_gap(con, gap):
    sql = (SQL_DIR / "05_reactivation.sql").read_text()
    sql = sql.replace("__GAP_PLUS_1__", str(gap + 1)).replace("__GAP__", str(gap))
    return con.execute(sql).df()


def sensitivity(con):
    rows = []
    for g in GAPS:
        d = run_gap(con, g)
        rows.append({"dormancy_gap_months": g, "reactivation_events": int(d["reactivated"].sum()),
                     "dormant_account_months": int(d["dormant_accounts"].sum()),
                     "pooled_rate": round(d["reactivated"].sum() / d["dormant_accounts"].sum(), 4)})
    return pd.DataFrame(rows)


def main():
    tables, figs = pathlib.Path("reports/tables"), pathlib.Path("reports/figures")
    tables.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)
    con = connect()
    allm = run(con, "01_monthly_activity.sql")[["month", "active_share", "active_share_3m_avg"]]
    est = run(con, "04_established_activity.sql")
    re3 = run_gap(con, DEFAULT_GAP)
    sens = sensitivity(con)
    est.to_csv(tables / "established_activity.csv", index=False)
    re3.to_csv(tables / "reactivation_gap3.csv", index=False)
    sens.to_csv(tables / "reactivation_sensitivity.csv", index=False)

    print("established accounts:", int(est["n_established"].iloc[0]),
          "| months tracked:", len(est))
    both = allm.merge(est[["month", "active_share_established"]], on="month")
    both["year"] = both["month"].dt.year
    sel = both[both["month"].dt.month.between(4, 10)]
    yoy = sel.groupby("year")[["active_share", "active_share_established"]].mean().round(3)
    print("\nApr-Oct average active share by year (same months each year):")
    print(yoy.to_string())
    print("\nreactivation, by dormancy rule:")
    print(sens.to_string(index=False))
    print("\nreactivation rate (gap 3), last 6 months with data:")
    print(re3.dropna().tail(6).assign(month=lambda d: d["month"].dt.strftime("%Y-%m"))
          .round(4).to_string(index=False))

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(allm["month"], allm["active_share"], color="#9bb7d4", lw=1, label="All 5,014 accounts")
    ax.plot(allm["month"], allm["active_share_3m_avg"], color="#1f5fa8", lw=2, label="All accounts, 3-month average")
    ax.plot(est["month"], est["active_share_established"], color="#e3a58a", lw=1,
            label="Established accounts (bought in Jan-Mar 2018)")
    ax.plot(est["month"], est["active_share_3m_avg"], color="#c4501f", lw=2, label="Established, 3-month average")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Share of accounts that bought in the month")
    ax.set_title("Monthly activity, Jan 2018 - Oct 2022 (observational; not churn)")
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(figs / "active_share.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    for g in GAPS:
        d = run_gap(con, g)
        r = d["reactivation_rate"].rolling(3, min_periods=1).mean()
        ax.plot(d["month"], r, lw=2.2 if g == DEFAULT_GAP else 1,
                label=f"dormant after {g} quiet months" + (" (main)" if g == DEFAULT_GAP else ""))
    ax.set_ylabel("Share of dormant accounts that bought again (3-month avg)")
    ax.set_title("Reactivation rate (observational; 2018 not comparable with later years)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(figs / "reactivation_rate.png", dpi=150)
    plt.close(fig)
    print("\nsaved tables to reports/tables and charts to reports/figures")


if __name__ == "__main__":
    main()
