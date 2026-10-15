"""Step 5: explainable RFM segments, stability check, cautious profile. Observational only."""
import pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from src.sql_metrics import SQL_DIR, SURVEY, connect

REF_NOW = "2022-10-31"
REF_PREV = "2021-10-31"
MIN_CELL = 30
ORDER = ["Frequent big spenders", "Frequent light spenders", "Occasional big spenders",
         "Occasional light spenders", "Lapsed"]
PROFILE_VARS = ["age_group", "income_bracket", "shopping_freq"]


def run_rfm(con, ref_date):
    sql = (SQL_DIR / "08_rfm.sql").read_text().replace("__REF_DATE__", ref_date)
    return con.execute(sql).df()


def compare_segments(prev, now):
    """Accounts that exist at both reference dates, with their segment at each."""
    return prev[["user_id", "segment"]].merge(now[["user_id", "segment"]], on="user_id",
                                              suffixes=("_prev", "_now"))


def stability(merged):
    """Share staying in the same segment, chance level, kappa (0 = chance, 1 = identical)."""
    observed = float((merged["segment_prev"] == merged["segment_now"]).mean())
    p0 = merged["segment_prev"].value_counts(normalize=True)
    p1 = merged["segment_now"].value_counts(normalize=True)
    expected = float(sum(p0.get(k, 0) * p1.get(k, 0) for k in set(p0.index) | set(p1.index)))
    kappa = (observed - expected) / (1 - expected)
    trans = pd.crosstab(merged["segment_prev"], merged["segment_now"], normalize="index")
    return {"observed_agreement": observed, "chance_agreement": expected, "kappa": kappa,
            "accounts": len(merged)}, trans


def survey_profile(con):
    return con.execute(
        'SELECT "Survey ResponseID" AS user_id, "Q-demos-age" AS age_group, '
        '"Q-demos-income" AS income_bracket, "Q-amazon-use-how-oft" AS shopping_freq '
        f"FROM read_csv_auto('{SURVEY}')").df()


def profile(seg, survey, var, min_cell=MIN_CELL):
    """Who is in each segment. ratio > 1 means more common in the segment than overall."""
    d = seg[["user_id", "segment"]].merge(survey[["user_id", var]], on="user_id")
    overall = d[var].value_counts(normalize=True).rename("overall_share")
    cell = d.groupby(["segment", var]).size().rename("accounts").reset_index()
    cell = cell.merge(d.groupby("segment").size().rename("segment_accounts"), on="segment")
    cell["share_of_segment"] = cell["accounts"] / cell["segment_accounts"]
    cell = cell.merge(overall, left_on=var, right_index=True)
    cell["ratio"] = cell["share_of_segment"] / cell["overall_share"]
    cell = cell[cell["accounts"] >= min_cell]
    return (cell.rename(columns={var: "level"}).assign(variable=var)
            [["variable", "level", "segment", "accounts", "share_of_segment", "overall_share", "ratio"]])


def summary(seg):
    tot_spend = seg["monetary_12m"].sum()
    g = seg.groupby("segment").agg(accounts=("user_id", "size"),
                                   median_recency_days=("recency_days", "median"),
                                   median_order_days_12m=("frequency_12m", "median"),
                                   median_spend_12m=("monetary_12m", "median"),
                                   spend_12m=("monetary_12m", "sum")).reindex(ORDER).dropna(how="all")
    g["share_of_accounts"] = g["accounts"] / g["accounts"].sum()
    g["share_of_12m_spend"] = g["spend_12m"] / tot_spend
    return g


def main():
    tables, figs = pathlib.Path("reports/tables"), pathlib.Path("reports/figures")
    tables.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)
    con = connect()
    now, prev = run_rfm(con, REF_NOW), run_rfm(con, REF_PREV)
    now.to_csv(f"data/processed/rfm_segments_{REF_NOW}.csv", index=False)   # has IDs: git-ignored
    print(f"cut-offs at {REF_NOW} (non-lapsed accounts): order-days in 12 months >= {now['f_med'].iloc[0]:g}"
          f" = frequent; 12-month spend >= ${now['m_med'].iloc[0]:,.0f} = big")
    print(f"cut-offs at {REF_PREV}: order-days >= {prev['f_med'].iloc[0]:g}; spend >= ${prev['m_med'].iloc[0]:,.0f}")

    s_now, s_prev = summary(now), summary(prev)
    s_now.to_csv(tables / "rfm_segment_summary.csv")
    print("\nsegments as of", REF_NOW)
    print(s_now.round(3).to_string())
    print("\nsegment sizes as of", REF_PREV, "(accounts, share)")
    print(pd.DataFrame({"accounts": s_prev["accounts"], "share": s_prev["share_of_accounts"].round(3)}).to_string())

    stab, trans = stability(compare_segments(prev, now))
    trans.reindex(index=ORDER, columns=ORDER).round(3).to_csv(tables / "rfm_stability_transitions.csv")
    print("\nstability, same accounts one year apart:", {k: round(v, 3) for k, v in stab.items()})
    print("where accounts moved (row = segment a year earlier, share per row):")
    print(trans.reindex(index=ORDER, columns=ORDER).round(2).to_string())

    sv = survey_profile(con)
    prof = pd.concat([profile(now, sv, v) for v in PROFILE_VARS])
    prof.to_csv(tables / "rfm_profile.csv", index=False)
    for v in PROFILE_VARS:
        p = prof[prof["variable"] == v]
        wide = p.pivot(index="level", columns="segment", values="ratio").reindex(columns=ORDER)
        wide.insert(0, "overall_share", p.drop_duplicates("level").set_index("level")["overall_share"])
        print(f"\nprofile by {v} (ratio vs overall; >1 = more common in segment; blank = fewer than {MIN_CELL} accounts)")
        print(wide.round(2).to_string())

    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = range(len(s_now))
    ax.bar([i - 0.2 for i in x], s_now["share_of_accounts"] * 100, 0.4, label="Share of accounts", color="#9bb7d4")
    ax.bar([i + 0.2 for i in x], s_now["share_of_12m_spend"] * 100, 0.4, label="Share of last-12-month spend", color="#c4501f")
    ax.set_xticks(list(x))
    ax.set_xticklabels([n.replace(" ", "\n", 1) for n in s_now.index], fontsize=8)
    ax.set_ylabel("%")
    ax.set_title(f"RFM segments as of {REF_NOW} (observational; gift cards excluded)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(figs / "rfm_segments.png", dpi=150)
    plt.close(fig)
    print("\nsaved tables and chart")


if __name__ == "__main__":
    main()
