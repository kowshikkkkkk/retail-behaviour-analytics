import os
import pathlib
import duckdb
import numpy as np
import pandas as pd
import pytest
from statsmodels.stats.proportion import proportion_confint
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize
from src.ab_simulation import (sample_size_two_proportions, power_two_proportions, wilson,
                               true_revenue_effect, simulate_experiment, run_scenario, load_pool)
from src.activity import run_gap
from tests.test_activity import reactivation_rows

EMPTY_SURVEY = pd.DataFrame({"user_id": pd.Series(dtype="string"),
                             "shopping_freq": pd.Series(dtype="string"),
                             "age_group": pd.Series(dtype="string")})


def fake_pool(n=40000, p=0.2, seed=0):
    rng = np.random.default_rng(seed)
    bought = (rng.random(n) < p).astype(float)
    spend = bought * rng.gamma(2.0, 40.0, n)           # buyers spend about $80
    return bought, spend


def test_sample_size_known_value_and_matches_statsmodels():
    assert sample_size_two_proportions(0.50, 0.55) == 1565                # textbook value
    h = proportion_effectsize(0.55, 0.50)
    sm = NormalIndPower().solve_power(effect_size=h, alpha=0.05, power=0.8, ratio=1.0)
    assert sample_size_two_proportions(0.50, 0.55) == pytest.approx(sm, rel=0.02)


def test_power_formula_consistent_with_sample_size():
    n = sample_size_two_proportions(0.2, 0.23)
    assert 0.80 <= power_two_proportions(0.2, 0.23, n) < 0.805
    assert power_two_proportions(0.2, 0.23, n // 4) < 0.45              # a quarter of the sample: far less power


def test_wilson_matches_statsmodels():
    lo, hi = wilson(50, 1000)
    slo, shi = proportion_confint(50, 1000, method="wilson")
    assert lo == pytest.approx(slo, abs=1e-6) and hi == pytest.approx(shi, abs=1e-6)


def test_true_revenue_effect_hand_checked():
    bought = np.array([1.0, 0, 0, 0])
    spend = np.array([100.0, 0, 0, 0])                                  # p0 = 0.25, buyers spend 100, r0 = 25
    assert true_revenue_effect(bought, spend, lift=0.05, discount=0.10) == pytest.approx(0.9 * (25 + 5) - 25)


def test_randomisation_arms_equal_and_no_effect_means_no_difference():
    bought, spend = fake_pool()
    rng = np.random.default_rng(1)
    bt, bc, st, sc = simulate_experiment(bought, spend, 5000, lift=0.0, discount=0.0, rng=rng)
    assert len(bt) == len(bc) == 5000
    assert abs(bt.mean() - bc.mean()) < 0.03
    assert abs(st.mean() - sc.mean()) < 0.1 * spend.mean()


def test_planted_lift_and_discount_are_recovered():
    bought, spend = fake_pool(n=60000)
    rng = np.random.default_rng(2)
    bt, bc, st, sc = simulate_experiment(bought, spend, 40000, lift=0.03, discount=0.10, rng=rng)
    assert bt.mean() - bc.mean() == pytest.approx(0.03, abs=0.006)
    expected = true_revenue_effect(bought, spend, 0.03, 0.10)
    assert st.mean() - sc.mean() == pytest.approx(expected, abs=0.15 * spend.mean())


def test_method_has_roughly_5_percent_false_positives_and_planned_power():
    bought, spend = fake_pool()
    p0 = bought.mean()
    n = sample_size_two_proportions(p0, p0 + 0.03)
    aa = run_scenario(bought, spend, n, lift=0.0, discount=0.0, n_sim=600, seed=11)
    assert 0.02 <= aa["significant_rate"] <= 0.09                         # about 5% by chance
    ab = run_scenario(bought, spend, n, lift=0.03, discount=0.0, n_sim=600, seed=12)
    assert 0.74 <= ab["significant_rate"] <= 0.86                         # about the planned 80%
    assert ab["ci_covers_true_lift"] == pytest.approx(0.95, abs=0.04)
    assert ab["mean_estimated_lift_pp"] == pytest.approx(3.0, abs=0.3)


def test_underpowered_experiments_overstate_the_lift_among_winners():
    bought, spend = fake_pool()
    r = run_scenario(bought, spend, 400, lift=0.03, discount=0.0, n_sim=800, seed=13)
    assert r["significant_rate"] < 0.35
    assert r["mean_lift_if_significant_positive_pp"] > 4.5               # winners look bigger than the true 3 pp


def test_same_seed_same_result():
    bought, spend = fake_pool(n=5000)
    a = run_scenario(bought, spend, 300, 0.03, 0.1, n_sim=100, seed=5)
    b = run_scenario(bought, spend, 300, 0.03, 0.1, n_sim=100, seed=5)
    assert a == b


def test_pool_sql_matches_reactivation_totals_and_spend():
    rows = reactivation_rows()
    p = pd.DataFrame(rows, columns=["user_id", "date", "qty", "spend", "is_gift"])
    p["date"] = pd.to_datetime(p["date"])
    con = duckdb.connect()
    con.register("purchases", p)
    con.register("survey_min", EMPTY_SURVEY)
    pool = load_pool(con, 3)
    monthly = run_gap(con, 3).set_index("month")
    assert len(pool) == int(monthly["dormant_accounts"].sum())
    assert int(pool["bought"].sum()) == int(monthly["reactivated"].sum())
    assert (pool.loc[pool["bought"] == 0, "spend_in_month"] == 0).all()
    assert (pool.loc[pool["bought"] == 1, "spend_in_month"] == 10.0).all()   # every real purchase there is $10


PARQUET = pathlib.Path("data/processed/purchases_clean.parquet")


@pytest.mark.skipif(os.environ.get("RUN_REAL_DATA") != "1" or not PARQUET.exists(),
                    reason="needs the real cleaned parquet; set RUN_REAL_DATA=1")
def test_real_pool_matches_earlier_reactivation_numbers():
    from src.sql_metrics import connect
    pool = load_pool(connect(), 3)
    assert len(pool) == 34930
    assert int(pool["bought"].sum()) == 7531
    assert round(pool["bought"].mean(), 4) == 0.2156
