"""Step 6: bootstrap confidence intervals and two hypothesis tests.

Intervals measure sampling noise INSIDE this volunteer sample only. They do not correct for who
volunteered. Everything here is observational.
"""
import pathlib
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, mannwhitneyu, rankdata
from src.monetization import gini, top_share
from src.segmentation import REF_NOW, run_rfm
from src.sql_metrics import SQL_DIR, SURVEY, connect, run

N_BOOT = 2000
SEED = 42
MEANINGFUL_DELTA = 0.147   # Cliff's delta: below this is called negligible (fixed before seeing results)
MEANINGFUL_PP = 3.0        # lapse-rate difference in percentage points (fixed before seeing results)
SINGLE_LABEL = "1 (just me!)"


# ---------- data ----------
def run_react(con, gap=3):
    sql = (SQL_DIR / "09_user_reactivation.sql").read_text()
    sql = sql.replace("__GAP_PLUS_1__", str(gap + 1)).replace("__GAP__", str(gap))
    return con.execute(sql).df()


def life_event_group(value):
    """moved_only / lost_job_only / none (blank = nothing ticked, an ASSUMPTION) / other."""
    if pd.isna(value):
        return "none"
    events = {x.strip() for x in str(value).split(",") if x.strip()}
    if events == {"Moved place of residence"}:
        return "moved_only"
    if events == {"Lost a job"}:
        return "lost_job_only"
    return "other"


def survey_inference(con):
    sv = con.execute(
        'SELECT "Survey ResponseID" AS user_id, "Q-amazon-use-howmany" AS people_on_account, '
        '"Q-life-changes" AS life_changes '
        f"FROM read_csv_auto('{SURVEY}')").df()
    sv["shared"] = sv["people_on_account"] != SINGLE_LABEL
    sv["event_group"] = sv["life_changes"].map(life_event_group)
    return sv[["user_id", "shared", "event_group"]]      # raw life-change text is dropped here


def build_features(con):
    users = run(con, "02_user_metrics.sql")[["user_id", "spend"]]
    rfm = run_rfm(con, REF_NOW)[["user_id", "segment", "monetary_12m"]]
    yr = run(con, "10_user_year_features.sql")
    react = run_react(con, 3)
    df = (users.merge(rfm, on="user_id").merge(yr, on="user_id")
          .merge(react, on="user_id").merge(survey_inference(con), on="user_id"))
    df["lapsed"] = (df["segment"] == "Lapsed").astype(float)
    df["is_fbs"] = (df["segment"] == "Frequent big spenders").astype(float)
    return df


# ---------- bootstrap ----------
STATS = {
    "median spend per account ($)": lambda a: float(np.median(a["spend"])),
    "mean spend per account ($)": lambda a: float(np.mean(a["spend"])),
    "top 10% share of spend": lambda a: top_share(a["spend"], 0.10),
    "Gini of spend": lambda a: gini(a["spend"]),
    "share of accounts lapsed (Oct 2022)": lambda a: float(a["lapsed"].mean()),
    "active share, Apr-Oct 2022": lambda a: float(a["active_months_apr_oct_2022"].mean() / 7),
    "Jan-Oct spend per account, 2022 / 2018": lambda a: float(a["spend_2022_jan_oct"].mean() / a["spend_2018_jan_oct"].mean()),
    "reactivation rate (3 quiet months, pooled)": lambda a: float(a["reactivations"].sum() / a["dormant_months"].sum()),
    "share of accounts: frequent big spenders": lambda a: float(a["is_fbs"].mean()),
    "share of 12-month spend: frequent big spenders": lambda a: float((a["monetary_12m"] * a["is_fbs"]).sum() / a["monetary_12m"].sum()),
}
BOOT_COLUMNS = ["spend", "lapsed", "active_months_apr_oct_2022", "spend_2022_jan_oct", "spend_2018_jan_oct",
                "reactivations", "dormant_months", "is_fbs", "monetary_12m"]


def bootstrap_all(stats, arrays, n_boot=N_BOOT, seed=SEED):
    """Resample WHOLE ACCOUNTS (not rows) with replacement; same draws for every statistic."""
    rng = np.random.default_rng(seed)
    n = len(next(iter(arrays.values())))
    est = {k: f(arrays) for k, f in stats.items()}
    draws = {k: np.empty(n_boot) for k in stats}
    for b in range(n_boot):
        idx = rng.integers(0, n, n)
        sub = {k: v[idx] for k, v in arrays.items()}
        for k, f in stats.items():
            draws[k][b] = f(sub)
    rows = []
    for k in stats:
        lo, hi = np.percentile(draws[k], [2.5, 97.5])
        rows.append({"statistic": k, "estimate": est[k], "ci_low": float(lo), "ci_high": float(hi)})
    return pd.DataFrame(rows)


def bootstrap_two_groups(x, y, stat, n_boot=N_BOOT, seed=SEED):
    """Resample each group separately; returns (estimate, ci_low, ci_high) for stat(x, y)."""
    rng = np.random.default_rng(seed)
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    est = float(stat(x, y))
    draws = np.empty(n_boot)
    for b in range(n_boot):
        draws[b] = stat(x[rng.integers(0, len(x), len(x))], y[rng.integers(0, len(y), len(y))])
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return est, float(lo), float(hi)


# ---------- hypothesis tests ----------
def cliffs_delta(x, y):
    """P(x > y) - P(x < y). Ranges from -1 to 1; 0 means no tendency either way."""
    n1, n2 = len(x), len(y)
    ranks = rankdata(np.concatenate([x, y]))
    u1 = ranks[:n1].sum() - n1 * (n1 + 1) / 2
    return float(2 * u1 / (n1 * n2) - 1)


def holm(pvals):
    """Holm-adjusted p-values (controls the chance of at least one false alarm across the family)."""
    p = np.asarray(pvals, dtype=float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(p) - rank) * p[i]))
        adj[i] = running
    return adj


def compare_rate(event, none):
    """2x2 chi-square (with continuity correction), plus Cramer's V from the uncorrected statistic."""
    event, none = np.asarray(event, dtype=float), np.asarray(none, dtype=float)
    if len(event) == 0 or len(none) == 0:
        raise ValueError(f"empty comparison group (event n={len(event)}, none n={len(none)}); "
                         "check how life_changes is being parsed")
    table = np.array([[event.sum(), len(event) - event.sum()], [none.sum(), len(none) - none.sum()]])
    _, p, _, _ = chi2_contingency(table, correction=True)
    chi2_nc = chi2_contingency(table, correction=False)[0]
    n = table.sum()
    return {"event_rate": float(event.mean()), "none_rate": float(none.mean()),
            "diff_pp": float((event.mean() - none.mean()) * 100), "p_value": float(p),
            "cramers_v": float(np.sqrt(chi2_nc / n))}


def fmt_p(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def main():
    tables = pathlib.Path("reports/tables")
    tables.mkdir(parents=True, exist_ok=True)
    con = connect()
    df = build_features(con)
    arrays = {c: df[c].to_numpy(dtype=float) for c in BOOT_COLUMNS}

    ci = bootstrap_all(STATS, arrays)
    ci.to_csv(tables / "headline_confidence_intervals.csv", index=False)
    print(f"95% bootstrap intervals ({N_BOOT} resamples of whole accounts, seed {SEED}, n = {len(df)} accounts)")
    print("These show noise inside this volunteer sample only; they do not fix who volunteered.\n")
    for r in ci.itertuples():
        print(f"{r.statistic:<50} {r.estimate:>12,.4f}   [{r.ci_low:,.4f}, {r.ci_high:,.4f}]")

    rows = []
    # ---- Test 1: shared vs single-person accounts, total spend ----
    x = df.loc[df["shared"], "spend"].to_numpy(dtype=float)
    y = df.loc[~df["shared"], "spend"].to_numpy(dtype=float)
    u = mannwhitneyu(x, y, alternative="two-sided")
    med = bootstrap_two_groups(x, y, lambda a, b: np.median(a) - np.median(b))
    dl = bootstrap_two_groups(x, y, cliffs_delta)
    print("\nTEST 1 (observational): total spend, accounts shared with others vs single-person accounts")
    print(f"  groups: shared n={len(x)}, single n={len(y)} | medians: ${np.median(x):,.0f} vs ${np.median(y):,.0f}")
    print(f"  median difference (shared - single): ${med[0]:,.0f}  95% CI [${med[1]:,.0f}, ${med[2]:,.0f}]")
    print(f"  Mann-Whitney p = {fmt_p(u.pvalue)}; Cliff's delta = {dl[0]:.3f}  95% CI [{dl[1]:.3f}, {dl[2]:.3f}]")
    print(f"  CI excludes 0: {'yes' if dl[1] > 0 or dl[2] < 0 else 'no'} | "
          f"|delta| >= {MEANINGFUL_DELTA} (pre-set): {'yes' if abs(dl[0]) >= MEANINGFUL_DELTA else 'no, negligible'}")
    rows.append({"test": "shared vs single spend", "n_a": len(x), "n_b": len(y), "effect": dl[0],
                 "ci_low": dl[1], "ci_high": dl[2], "p_raw": u.pvalue, "p_adjusted": u.pvalue})

    # ---- Test 2: lapse rate, life event vs none ----
    none = df.loc[df["event_group"] == "none", "lapsed"].to_numpy()
    comps = []
    for name in ["moved_only", "lost_job_only"]:
        ev = df.loc[df["event_group"] == name, "lapsed"].to_numpy()
        r = compare_rate(ev, none)
        ci_pp = bootstrap_two_groups(ev, none, lambda a, b: (a.mean() - b.mean()) * 100)
        comps.append((name, ev, r, ci_pp))
    adj = holm([c[2]["p_value"] for c in comps])
    print("\nTEST 2 (EXPLORATORY, observational): lapsed at Oct 2022 (no purchase in 180 days), 2021 life event vs none")
    print("  caveats: blank answer assumed = no event (cannot be checked); event may have hit someone else on the")
    print("  account; timing within 2021 unknown; not adjusted for age or income. 'Other/multiple' answers excluded.")
    print(f"  comparison group 'none': n={len(none)}, lapse rate {none.mean() * 100:.1f}%")
    for (name, ev, r, ci_pp), pa in zip(comps, adj):
        print(f"  {name}: n={len(ev)}, lapse rate {r['event_rate'] * 100:.1f}% | difference {r['diff_pp']:+.1f} pp "
              f"95% CI [{ci_pp[1]:+.1f}, {ci_pp[2]:+.1f}] | chi-square p = {fmt_p(r['p_value'])}, "
              f"Holm-adjusted {fmt_p(pa)} | Cramer's V = {r['cramers_v']:.3f}")
        print(f"     CI excludes 0: {'yes' if ci_pp[1] > 0 or ci_pp[2] < 0 else 'no'} | "
              f"|difference| >= {MEANINGFUL_PP:g} pp (pre-set): {'yes' if abs(r['diff_pp']) >= MEANINGFUL_PP else 'no'}")
        rows.append({"test": f"lapsed: {name} vs none", "n_a": len(ev), "n_b": len(none), "effect": r["diff_pp"],
                     "ci_low": ci_pp[1], "ci_high": ci_pp[2], "p_raw": r["p_value"], "p_adjusted": pa})
    pd.DataFrame(rows).to_csv(tables / "hypothesis_tests.csv", index=False)
    print("\nsaved reports/tables/headline_confidence_intervals.csv and hypothesis_tests.csv")


if __name__ == "__main__":
    main()
