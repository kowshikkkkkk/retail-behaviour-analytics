"""Dashboard. Reads ONLY the aggregate tables in reports/tables: no raw data and no account IDs.

Run from the project root:  streamlit run app/streamlit_app.py
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TABLES = ROOT / "reports" / "tables"
FIGS = ROOT / "reports" / "figures"

st.set_page_config(page_title="Retail behaviour analytics", layout="wide")


@st.cache_data
def load(name, **kw):
    path = TABLES / name
    return pd.read_csv(path, **kw) if path.exists() else None


def have(df, name, cmd):
    if df is None:
        st.warning(f"Missing reports/tables/{name}. Run `{cmd}` first.")
        return False
    return True


def fmt_stat(name, v):
    if "($)" in name:
        return f"${v:,.0f}"
    if "2022 / 2018" in name:
        return f"{v:.2f}x"
    if "Gini" in name:
        return f"{v:.3f}"
    return f"{v * 100:.1f}%"


def fmt_conc(name, v):
    if name in ("accounts",):
        return f"{v:,.0f}"
    if name == "gini":
        return f"{v:.3f}"
    if "share" in name:
        return f"{v * 100:.1f}%"
    return f"${v:,.0f}"


st.title("Retail behaviour analytics")
st.caption("5,014 volunteer Amazon accounts, Jan 2018 to Oct 2022 (Open e-commerce 1.0, CC0). "
           "Everything is observational unless marked SIMULATION. This is a volunteer sample, not Amazon shoppers.")

tabs = st.tabs(["Summary", "Activity", "Spend", "Segments", "Tests", "A/B simulation", "Limits"])

# ---------------- Summary ----------------
with tabs[0]:
    ci = load("headline_confidence_intervals.csv")
    if have(ci, "headline_confidence_intervals.csv", "python -m src.inference"):
        ci = ci.set_index("statistic")
        picks = ["share of 12-month spend: frequent big spenders", "top 10% share of spend",
                 "Jan-Oct spend per account, 2022 / 2018", "reactivation rate (3 quiet months, pooled)"]
        cols = st.columns(len(picks))
        for c, p in zip(cols, picks):
            if p in ci.index:
                r = ci.loc[p]
                c.metric(p, fmt_stat(p, r["estimate"]),
                         help=f"95% bootstrap interval {fmt_stat(p, r['ci_low'])} to {fmt_stat(p, r['ci_high'])}")
        table = pd.DataFrame({"estimate": [fmt_stat(i, r["estimate"]) for i, r in ci.iterrows()],
                              "95% interval": [f"{fmt_stat(i, r['ci_low'])} to {fmt_stat(i, r['ci_high'])}"
                                               for i, r in ci.iterrows()]}, index=ci.index)
        st.dataframe(table, width="stretch")
        st.caption("Intervals come from resampling whole accounts 2,000 times. They show noise inside this "
                   "volunteer sample only; they do not correct for who volunteered.")

# ---------------- Activity ----------------
with tabs[1]:
    m, e, r = (load("monthly_activity.csv"), load("established_activity.csv"), load("reactivation_gap3.csv"))
    if have(m, "monthly_activity.csv", "python -m src.sql_metrics") and have(e, "established_activity.csv", "python -m src.activity"):
        a = m[["month", "active_share_3m_avg"]].rename(columns={"active_share_3m_avg": "All accounts"})
        b = e[["month", "active_share_3m_avg"]].rename(columns={"active_share_3m_avg": "Established accounts"})
        d = a.merge(b, on="month", how="left")
        d["month"] = pd.to_datetime(d["month"])
        st.subheader("Share of accounts that bought in the month (3-month average)")
        st.line_chart(d.set_index("month"))
        st.caption("OBSERVATIONAL. 'Established' = accounts that bought in Jan to Mar 2018, tracked from April 2018. "
                   "This is activity, not retention or churn: everyone here still had an account in late 2022. "
                   "December peaks are holiday shopping. Nov and Dec 2022 are excluded because histories are incomplete.")
    if have(r, "reactivation_gap3.csv", "python -m src.activity"):
        r = r.copy()
        r["month"] = pd.to_datetime(r["month"])
        r["3-month average"] = r["reactivation_rate"].rolling(3, min_periods=1).mean()
        st.subheader("Quiet accounts that buy again (dormant = no purchase in the previous 3 months)")
        st.line_chart(r.set_index("month")[["3-month average"]])
        st.caption("OBSERVATIONAL. 2018 is not comparable with later years: the quiet pool changes composition "
                   "(early on it can only hold recently quiet accounts).")

# ---------------- Spend ----------------
with tabs[2]:
    yr = load("spend_by_year_jan_oct.csv")
    conc = load("spend_concentration.csv", index_col=0)
    cat = load("category_mix.csv")
    if have(yr, "spend_by_year_jan_oct.csv", "python -m src.monetization"):
        st.subheader("Spend per account, Jan to Oct of each year")
        st.bar_chart(yr.assign(year=yr["year"].astype(str)).set_index("year")[["spend_per_account"]])
        st.caption("OBSERVATIONAL. Current dollars, not adjusted for inflation. Same months every year.")
        st.dataframe(yr.set_index("year").round(1), width="stretch")
    if have(conc, "spend_concentration.csv", "python -m src.monetization"):
        st.subheader("How concentrated is spend?")
        keep = ["accounts", "median", "mean", "p90", "p99", "top_1pct_share", "top_10pct_share", "gini",
                "share_of_accounts_for_half_of_spend"]
        show = conc.loc[[k for k in keep if k in conc.index]]
        st.dataframe(pd.DataFrame({c: [fmt_conc(i, v) for i, v in show[c].items()] for c in show.columns},
                                  index=show.index), width="stretch")
        img = FIGS / "spend_concentration.png"
        if img.exists():
            st.image(str(img), width=420)
    if have(cat, "category_mix.csv", "python -m src.monetization"):
        st.subheader("Where spend goes")
        st.bar_chart(cat.set_index("category_group")[["share_of_spend"]])
        st.caption("Amazon product types are very granular (1,872 of them), so no single type is large. "
                   "Sensitive categories are merged into one bucket and never broken out. Gift cards are excluded.")

# ---------------- Segments ----------------
with tabs[3]:
    seg = load("rfm_segment_summary.csv", index_col=0)
    tr = load("rfm_stability_transitions.csv", index_col=0)
    prof = load("rfm_profile.csv")
    if have(seg, "rfm_segment_summary.csv", "python -m src.segmentation"):
        st.subheader("RFM segments as of 31 Oct 2022")
        st.markdown("Lapsed = no purchase in 180 days. Everyone else is split at the median of non-lapsed accounts: "
                    "**frequent** = at or above the median number of shopping days in 12 months; "
                    "**big** = at or above the median 12-month spend.")
        st.bar_chart((seg[["share_of_accounts", "share_of_12m_spend"]] * 100).rename(
            columns={"share_of_accounts": "% of accounts", "share_of_12m_spend": "% of 12-month spend"}))
        nice = seg.copy()
        nice["share_of_accounts"] = (nice["share_of_accounts"] * 100).round(1)
        nice["share_of_12m_spend"] = (nice["share_of_12m_spend"] * 100).round(1)
        st.dataframe(nice.round(1), width="stretch")
    if have(tr, "rfm_stability_transitions.csv", "python -m src.segmentation"):
        st.subheader("Where accounts moved one year later")
        st.caption("Each row sums to 100%: the segment a year earlier (rows) against now (columns).")
        st.dataframe((tr * 100).round(0).astype(int), width="stretch")
    if have(prof, "rfm_profile.csv", "python -m src.segmentation"):
        st.subheader("Who is in each segment")
        st.caption("Ratio above 1 = more common in that segment than overall. Cells under 30 accounts are hidden. "
                   "Descriptive only; age and income overlap and are not separated.")
        for v in prof["variable"].unique():
            with st.expander(v):
                p = prof[prof["variable"] == v]
                st.dataframe(p.pivot(index="level", columns="segment", values="ratio").round(2),
                             width="stretch")

# ---------------- Tests ----------------
with tabs[4]:
    ht = load("hypothesis_tests.csv")
    if have(ht, "hypothesis_tests.csv", "python -m src.inference"):
        rows = []
        for _, x in ht.iterrows():
            spend_test = "spend" in x["test"]
            eff = f"{x['effect']:.3f} (Cliff's delta)" if spend_test else f"{x['effect']:+.1f} percentage points"
            ci_txt = f"{x['ci_low']:.3f} to {x['ci_high']:.3f}" if spend_test else f"{x['ci_low']:+.1f} to {x['ci_high']:+.1f}"
            p = lambda v: "<0.001" if v < 0.001 else f"{v:.3f}"
            rows.append({"test": x["test"], "group sizes": f"{int(x['n_a']):,} vs {int(x['n_b']):,}", "effect": eff,
                         "95% interval": ci_txt, "p (raw)": p(x["p_raw"]), "p (adjusted)": p(x["p_adjusted"])})
        st.dataframe(pd.DataFrame(rows).set_index("test"), width="stretch")
        st.markdown(
            "- **Shared vs single-person accounts:** a big difference, but mostly mechanical (more people on an account "
            "buy more).\n"
            "- **Life events vs lapsing:** EXPLORATORY. No detectable difference. A blank answer is assumed to mean "
            "no event (cannot be checked), the event may have hit someone else on the account, and nothing is adjusted "
            "for age or income.\n"
            "- With about 5,000 accounts even tiny differences can be 'significant', so the effect sizes and intervals "
            "matter more than the p-values.")

# ---------------- A/B simulation ----------------
with tabs[5]:
    st.warning("SIMULATION. Nobody was randomly assigned to anything. Baseline behaviour is real; the groups and the "
               "effect are planted, so we know the true answer and can check the method. It says nothing about "
               "whether a real coupon would work.")
    st.markdown("Scenario: a 10%-off coupon sent to accounts that have been quiet for 3 months. Primary metric: bought "
                "in the month. Guardrail: spend per account must not be significantly lower.")
    ss = load("ab_sample_size.csv")
    sim = load("ab_simulation_results.csv", index_col=0)
    ex = load("ab_example_experiment.csv")
    re_ = load("reactivation_gap3.csv")
    if have(ss, "ab_sample_size.csv", "python -m src.ab_simulation"):
        st.subheader("Sample size (5% significance, 80% power)")
        st.dataframe(ss.set_index("detectable_lift_pp"), width="stretch")
        st.caption("The months column is rough: it assumes fresh enrollable quiet accounts keep arriving at the "
                   "recent monthly volume.")
    if have(sim, "ab_simulation_results.csv", "python -m src.ab_simulation"):
        st.subheader("Does the method behave? (2,000 simulated experiments per row)")
        s = sim[["n_per_arm", "true_lift_pp", "significant_rate", "mean_estimated_lift_pp",
                 "mean_lift_if_significant_positive_pp", "ci_covers_true_lift", "guardrail_flag_rate",
                 "ship_rate", "true_spend_effect_dollars"]].copy()
        for c in ["significant_rate", "ci_covers_true_lift", "guardrail_flag_rate", "ship_rate"]:
            s[c] = (s[c] * 100).round(1)
        st.dataframe(s.round(2), width="stretch")
        st.caption("Rates are in %. With no effect about 5% should be significant by chance. With too few accounts "
                   "the 'winners' overstate the lift. A guardrail of 'not significantly lower' can miss a real revenue loss.")
    if have(ex, "ab_example_experiment.csv", "python -m src.ab_simulation"):
        x = ex.iloc[0]
        st.markdown(f"One simulated experiment: lift **{x['lift'] * 100:+.2f} points** "
                    f"(95% interval {x['ci_low'] * 100:+.2f} to {x['ci_high'] * 100:+.2f}), "
                    f"spend per account difference ${x['spend_diff']:+.2f}.")
    if re_ is not None:
        from src.ab_simulation import power_two_proportions, sample_size_two_proportions
        p0 = float(re_["reactivated"].sum() / re_["dormant_accounts"].sum())
        st.subheader("Try it: power for a given lift and size")
        c1, c2 = st.columns(2)
        lift = c1.slider("True lift (percentage points)", 1.0, 8.0, 3.0, 0.5)
        n = c2.slider("Accounts per arm", 200, 10000, 3000, 100)
        pw = power_two_proportions(p0, p0 + lift / 100, n)
        need = sample_size_two_proportions(p0, p0 + lift / 100)
        st.markdown(f"Baseline purchase rate {p0 * 100:.1f}%. With {n:,} accounts per arm the chance of detecting a "
                    f"+{lift:g} point lift is **{pw * 100:.0f}%**. For 80% you need **{need:,}** per arm.")

# ---------------- Limits ----------------
with tabs[6]:
    st.markdown("""
- **Volunteer sample.** Ages 25 to 34 are over-represented and these accounts shop a lot. Intervals only measure
  noise inside the sample, not who volunteered.
- **No churn.** Everyone still had an account in late 2022, and histories start in Jan 2018, so a first purchase here
  is not acquisition. This is activity and reactivation, not retention.
- **No refunds or returns** in the file. Spend is item price times quantity at purchase, in current dollars.
- **An account is not a person.** It can be a household.
- **An order is a proxy:** one account's purchases on one day.
- **Cleaning:** analysis window 2018-01-01 to 2022-10-31; gift cards left out of spend; exact duplicates kept; missing
  category labelled Unknown; sensitive categories merged into one bucket.
- **Privacy choices:** health, substance-use, race, gender and sexual-orientation survey columns are never read;
  groups under 30 accounts are hidden; no account-level data is shown here.
- **The A/B part is a simulation** and the guardrail rule is weaker than a proper non-inferiority margin.
""")
