"""Step 7b: a SIMULATED A/B test built on real dormant-account behaviour.

EVERYTHING HERE IS A SIMULATION. Nobody was randomly assigned to anything. Baseline behaviour (how often
dormant accounts buy again, and how much they spend) comes from the real data; the group assignment and the
treatment effect are planted by us, so we know the true answer and can check that the method finds it.
It says nothing about whether any real message or coupon would work.

Scenario: a "10% off" reactivation coupon sent to accounts that have been quiet for 3 months.
  Primary metric : bought in the month (yes/no)           -> two-proportion z-test
  Guardrail      : spend per account in the month (zeros included) must not be significantly LOWER (Welch t)
  Decision rule  : ship if primary is significantly positive AND the guardrail is not significantly negative
"""
import math
import pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm, t as t_dist
from src.sql_metrics import SQL_DIR, connect

ALPHA = 0.05
POWER = 0.80
PLANNED_LIFT = 0.03        # minimum effect worth detecting: +3 percentage points
DISCOUNT = 0.10            # the coupon takes 10% off every treated purchase
N_SIM = 2000
SEED = 2026
UNDERPOWERED_N = 500


# ---------- planning ----------
def sample_size_two_proportions(p0, p1, alpha=ALPHA, power=POWER):
    """Accounts needed PER ARM to detect p0 -> p1 with a two-sided test."""
    pbar = (p0 + p1) / 2
    za, zb = norm.ppf(1 - alpha / 2), norm.ppf(power)
    num = za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p0 * (1 - p0) + p1 * (1 - p1))
    return int(math.ceil((num / (p1 - p0)) ** 2))


def power_two_proportions(p0, p1, n, alpha=ALPHA):
    """Chance of a significant result if the true rates are p0 and p1 and each arm has n accounts."""
    pbar = (p0 + p1) / 2
    za = norm.ppf(1 - alpha / 2)
    return float(norm.cdf((abs(p1 - p0) * math.sqrt(n) - za * math.sqrt(2 * pbar * (1 - pbar)))
                          / math.sqrt(p0 * (1 - p0) + p1 * (1 - p1))))


def wilson(k, n, z=1.96):
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


# ---------- real baseline ----------
def load_pool(con, gap=3):
    sql = (SQL_DIR / "11_dormant_pool.sql").read_text()
    sql = sql.replace("__GAP_PLUS_1__", str(gap + 1)).replace("__GAP__", str(gap))
    df = con.execute(sql).df()
    return df


def true_revenue_effect(bought, spend, lift, discount):
    """Planted true change in spend per account (zeros included), in dollars."""
    r0 = spend.mean()
    buyer_mean = spend[bought == 1].mean()
    return (1 - discount) * (r0 + lift * buyer_mean) - r0


# ---------- simulation ----------
def simulate_experiment(bought, spend, n_per_arm, lift, discount, rng):
    """Draw 2n real dormant account-months, randomise n to treatment, plant the lift and the discount."""
    n2 = 2 * n_per_arm
    idx = rng.integers(0, len(bought), n2)
    b, s = bought[idx].copy(), spend[idx].copy()
    treat = np.zeros(n2, dtype=bool)
    treat[rng.permutation(n2)[:n_per_arm]] = True
    p0 = bought.mean()
    flip = treat & (b == 0) & (rng.random(n2) < lift / (1 - p0))     # non-buyers who now buy
    s[flip] = rng.choice(spend[bought == 1], int(flip.sum()))        # spend drawn from real buyers
    b[flip] = 1
    s[treat] = s[treat] * (1 - discount)
    return b[treat], b[~treat], s[treat], s[~treat]


def analyse(bt, bc, st, sc):
    n1, n0 = len(bt), len(bc)
    p1, p0 = bt.mean(), bc.mean()
    pooled = (bt.sum() + bc.sum()) / (n1 + n0)
    se0 = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n0))
    z = (p1 - p0) / se0
    p_primary = 2 * norm.sf(abs(z))
    se_u = math.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
    v1, v0 = st.var(ddof=1) / n1, sc.var(ddof=1) / n0
    tstat = (st.mean() - sc.mean()) / math.sqrt(v1 + v0)
    df = (v1 + v0) ** 2 / (v1 ** 2 / (n1 - 1) + v0 ** 2 / (n0 - 1))
    return {"lift": p1 - p0, "ci_low": p1 - p0 - 1.96 * se_u, "ci_high": p1 - p0 + 1.96 * se_u,
            "p_primary": p_primary, "spend_diff": st.mean() - sc.mean(),
            "p_guardrail_lower": float(t_dist.cdf(tstat, df))}


def run_scenario(bought, spend, n_per_arm, lift, discount, n_sim=N_SIM, seed=SEED):
    rng = np.random.default_rng(seed)
    res = pd.DataFrame([analyse(*simulate_experiment(bought, spend, n_per_arm, lift, discount, rng))
                        for _ in range(n_sim)])
    sig = res["p_primary"] < ALPHA
    pos = sig & (res["lift"] > 0)
    guard = res["p_guardrail_lower"] < ALPHA
    ship = pos & ~guard
    covered = (res["ci_low"] <= lift) & (lift <= res["ci_high"])
    k = int(sig.sum())
    lo, hi = wilson(k, n_sim)
    return {"n_per_arm": n_per_arm, "true_lift_pp": lift * 100, "discount": discount,
            "significant_rate": k / n_sim, "significant_rate_ci_low": lo, "significant_rate_ci_high": hi,
            "mean_estimated_lift_pp": res["lift"].mean() * 100,
            "mean_lift_if_significant_positive_pp": (res.loc[pos, "lift"].mean() * 100) if pos.any() else float("nan"),
            "ci_covers_true_lift": float(covered.mean()),
            "guardrail_flag_rate": float(guard.mean()), "ship_rate": float(ship.mean()),
            "mean_spend_diff_dollars": res["spend_diff"].mean()}


def main():
    tables, figs = pathlib.Path("reports/tables"), pathlib.Path("reports/figures")
    tables.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)
    pool = load_pool(connect())
    bought = pool["bought"].to_numpy(dtype=float)
    spend = pool["spend_in_month"].to_numpy(dtype=float)
    p0 = bought.mean()
    per_month = pool.groupby("month").size()
    recent = per_month.tail(12).mean()
    planned_n = sample_size_two_proportions(p0, p0 + PLANNED_LIFT)

    print("*** SIMULATION built on real dormant-account behaviour. Nothing here is a real experiment. ***")
    print("Scenario: 10%-off coupon sent to accounts quiet for 3 months.")
    print("Primary metric: bought in the month. Guardrail: spend per account (zeros included) must not drop.")
    print(f"\nreal baseline pool: {len(pool):,} dormant account-months | baseline purchase rate {p0 * 100:.2f}%"
          f" | mean spend per dormant account-month ${spend.mean():.2f} | buyers' mean ${spend[bought == 1].mean():.2f}")
    print(f"dormant accounts per month, last 12 months of data: about {recent:,.0f}")

    plan = pd.DataFrame({"detectable_lift_pp": [1, 2, 3, 5]})
    plan["n_per_arm"] = [sample_size_two_proportions(p0, p0 + d / 100) for d in plan["detectable_lift_pp"]]
    plan["total_accounts"] = plan["n_per_arm"] * 2
    plan["months_at_current_volume_(rough)"] = (plan["total_accounts"] / recent).round(1)
    plan.to_csv(tables / "ab_sample_size.csv", index=False)
    print(f"\nsample size for {ALPHA:.0%} significance and {POWER:.0%} power (two-sided):")
    print(plan.to_string(index=False))
    print("(months column is rough: it assumes about", f"{recent:,.0f}", "enrollable dormant accounts arrive each month)")

    scen = [("A/A: no effect, planned n", planned_n, 0.0, 0.0),
            ("A/B: +3 pp lift, planned n", planned_n, PLANNED_LIFT, DISCOUNT),
            ("A/B: +3 pp lift, too few accounts", UNDERPOWERED_N, PLANNED_LIFT, DISCOUNT),
            ("A/B: only +1 pp lift, planned n", planned_n, 0.01, DISCOUNT)]
    rows = []
    for name, n, lift, disc in scen:
        r = run_scenario(bought, spend, n, lift, disc)
        r["scenario"] = name
        r["true_spend_effect_dollars"] = true_revenue_effect(bought, spend, lift, disc)
        rows.append(r)
    out = pd.DataFrame(rows).set_index("scenario")
    out.to_csv(tables / "ab_simulation_results.csv")
    print(f"\n{N_SIM} simulated experiments per scenario (seed {SEED}):")
    show = out[["n_per_arm", "true_lift_pp", "significant_rate", "mean_estimated_lift_pp",
                "mean_lift_if_significant_positive_pp", "ci_covers_true_lift", "guardrail_flag_rate", "ship_rate",
                "true_spend_effect_dollars"]]
    print(show.round(3).to_string())
    aa = out.loc[scen[0][0]]
    print(f"\nA/A false-positive rate {aa['significant_rate'] * 100:.1f}% "
          f"(95% interval {aa['significant_rate_ci_low'] * 100:.1f}% to {aa['significant_rate_ci_high'] * 100:.1f}%; expect about 5%)")
    ab = out.loc[scen[1][0]]
    print(f"planned-n power {ab['significant_rate'] * 100:.1f}% "
          f"(95% interval {ab['significant_rate_ci_low'] * 100:.1f}% to {ab['significant_rate_ci_high'] * 100:.1f}%; "
          f"formula says {power_two_proportions(p0, p0 + PLANNED_LIFT, planned_n) * 100:.1f}%)")
    print(f"true change in spend per account planted in the +3 pp scenario: ${ab['true_spend_effect_dollars']:.2f}"
          f" (baseline ${spend.mean():.2f}), so the guardrail test is weak at this sample size")

    # one experiment, read the way you would read a real one
    rng = np.random.default_rng(7)
    ex = analyse(*simulate_experiment(bought, spend, planned_n, PLANNED_LIFT, DISCOUNT, rng))
    verdict = ("SHIP" if ex["p_primary"] < ALPHA and ex["lift"] > 0 and ex["p_guardrail_lower"] >= ALPHA
               else "DO NOT SHIP / INCONCLUSIVE")
    pd.DataFrame([ex]).to_csv(tables / "ab_example_experiment.csv", index=False)
    print(f"\none simulated experiment ({planned_n:,} per arm, planted true lift +3.0 pp):")
    p_txt = "<0.001" if ex["p_primary"] < 0.001 else f"{ex['p_primary']:.3f}"
    print(f"  lift {ex['lift'] * 100:+.2f} pp, 95% CI [{ex['ci_low'] * 100:+.2f}, {ex['ci_high'] * 100:+.2f}], p = {p_txt}")
    print("  (one random draw: single experiments scatter around the true +3.0 pp)")
    print(f"  spend per account difference ${ex['spend_diff']:+.2f}; guardrail 'significantly lower' p = {ex['p_guardrail_lower']:.3f}")
    print(f"  decision under the pre-set rule: {verdict}")

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ns = np.arange(100, 12001, 100)
    for d in (1, 2, 3, 5):
        ax.plot(ns, [power_two_proportions(p0, p0 + d / 100, n) * 100 for n in ns], label=f"true lift +{d} pp")
    ax.axhline(80, color="grey", ls="--", lw=1)
    ax.axvline(planned_n, color="grey", ls=":", lw=1)
    ax.set_xlabel("Accounts per arm")
    ax.set_ylabel("Chance of a significant result (%)")
    ax.set_title("SIMULATION planning: power vs sample size (baseline from real dormant accounts)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(figs / "ab_power_curve.png", dpi=150)
    plt.close(fig)
    print("\nsaved tables and chart")


if __name__ == "__main__":
    main()
