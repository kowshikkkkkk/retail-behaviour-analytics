import os
import pathlib
import duckdb
import numpy as np
import pandas as pd
import pytest
from scipy.stats import mannwhitneyu
from src.inference import (cliffs_delta, holm, life_event_group, compare_rate, bootstrap_all,
                           bootstrap_two_groups, run_react)
from src.sql_metrics import SQL_DIR
from tests.test_activity import brute_reactivation, reactivation_rows

EMPTY_SURVEY = pd.DataFrame({"user_id": pd.Series(dtype="string"),
                             "shopping_freq": pd.Series(dtype="string"),
                             "age_group": pd.Series(dtype="string")})


def test_cliffs_delta_known_values_and_matches_mannwhitney():
    assert cliffs_delta([1, 2, 3], [1, 2, 3]) == pytest.approx(0.0)
    assert cliffs_delta([3, 4], [1, 2]) == pytest.approx(1.0)
    assert cliffs_delta([1, 2], [3, 4]) == pytest.approx(-1.0)
    assert cliffs_delta([1, 2, 3], [2]) == pytest.approx(0.0)           # one win, one tie, one loss
    rng = np.random.default_rng(0)
    x, y = rng.normal(1, 1, 60), rng.normal(0, 1, 40)
    u = mannwhitneyu(x, y, alternative="two-sided").statistic
    assert cliffs_delta(x, y) == pytest.approx(2 * u / (60 * 40) - 1)


def test_holm_hand_checked():
    assert holm([0.01, 0.04]) == pytest.approx([0.02, 0.04])
    assert holm([0.04, 0.01]) == pytest.approx([0.04, 0.02])            # order of input does not matter
    assert holm([0.3, 0.6]) == pytest.approx([0.6, 0.6])                # capped by the running maximum


def test_life_event_group_parsing():
    assert life_event_group(np.nan) == "none"
    assert life_event_group("Moved place of residence") == "moved_only"
    assert life_event_group("Lost a job ") == "lost_job_only"           # trailing space in the real data
    assert life_event_group("Lost a job ,Moved place of residence") == "other"
    assert life_event_group("Divorce") == "other"


def test_compare_rate_hand_checked():
    event = [1] * 10 + [0] * 90          # 10% lapsed
    none = [1] * 20 + [0] * 80           # 20% lapsed
    r = compare_rate(event, none)
    assert r["diff_pp"] == pytest.approx(-10.0)
    assert r["cramers_v"] == pytest.approx(np.sqrt(3.9215686 / 200), rel=1e-4)   # chi-square 3.92 by hand
    assert 0.03 < r["p_value"] < 0.12


def test_bootstrap_is_reproducible_and_sane():
    rng = np.random.default_rng(1)
    a = {"v": rng.normal(10, 2, 400)}
    stats = {"mean": lambda d: float(d["v"].mean()), "const": lambda d: 7.0}
    t1 = bootstrap_all(stats, a, n_boot=500, seed=5)
    t2 = bootstrap_all(stats, a, n_boot=500, seed=5)
    assert t1.equals(t2)                                                  # same seed, same answer
    m = t1[t1["statistic"] == "mean"].iloc[0]
    assert m["ci_low"] < m["estimate"] < m["ci_high"]
    assert (m["ci_high"] - m["ci_low"]) == pytest.approx(2 * 1.96 * 2 / np.sqrt(400), rel=0.25)
    c = t1[t1["statistic"] == "const"].iloc[0]
    assert c["ci_low"] == c["ci_high"] == c["estimate"] == 7.0
    est, lo, hi = bootstrap_two_groups(a["v"][:200], a["v"][200:], lambda x, y: x.mean() - y.mean(),
                                       n_boot=300, seed=3)
    assert lo < est < hi


def test_user_reactivation_sql_matches_brute_force_and_monthly_totals():
    rows = reactivation_rows()
    p = pd.DataFrame(rows, columns=["user_id", "date", "qty", "spend", "is_gift"])
    p["date"] = pd.to_datetime(p["date"])
    con = duckdb.connect()
    con.register("purchases", p)
    con.register("survey_min", EMPTY_SURVEY)
    for gap in (2, 3, 4):
        per_user = run_react(con, gap)
        exp = brute_reactivation(p, gap)
        assert int(per_user["dormant_months"].sum()) == int(exp["dormant_accounts"].sum())
        assert int(per_user["reactivations"].sum()) == int(exp["reactivated"].sum())


def test_user_year_features():
    rows = [("u1", "2018-03-01", 10.0, False), ("u1", "2018-11-01", 99.0, False),   # Nov excluded
            ("u1", "2022-04-10", 5.0, False), ("u1", "2022-04-20", 5.0, False),       # same month counts once
            ("u1", "2022-07-01", 7.0, False), ("u1", "2022-02-01", 3.0, False),       # Feb: spend yes, not Apr-Oct
            ("u2", "2022-05-05", 20.0, False), ("u3", "2022-05-05", 500.0, True)]     # u3 gift only: not an account
    p = pd.DataFrame(rows, columns=["user_id", "date", "spend", "is_gift"])
    p["date"] = pd.to_datetime(p["date"])
    con = duckdb.connect()
    con.register("purchases", p)
    out = con.execute((SQL_DIR / "10_user_year_features.sql").read_text()).df().set_index("user_id")
    assert set(out.index) == {"u1", "u2"}
    assert out.loc["u1", "spend_2018_jan_oct"] == 10 and out.loc["u1", "spend_2022_jan_oct"] == 20
    assert out.loc["u1", "active_months_apr_oct_2022"] == 2 and out.loc["u2", "active_months_apr_oct_2022"] == 1
    assert out.loc["u2", "spend_2018_jan_oct"] == 0


PARQUET = pathlib.Path("data/processed/purchases_clean.parquet")


@pytest.mark.skipif(os.environ.get("RUN_REAL_DATA") != "1" or not PARQUET.exists(),
                    reason="needs the real cleaned parquet; set RUN_REAL_DATA=1")
def test_real_data_features_reproduce_earlier_numbers():
    from src.inference import build_features, STATS, BOOT_COLUMNS
    from src.sql_metrics import connect
    df = build_features(connect())
    a = {c: df[c].to_numpy(dtype=float) for c in BOOT_COLUMNS}
    assert len(df) == 5014
    assert round(STATS["median spend per account ($)"](a), 2) == 5166.15
    assert round(STATS["mean spend per account ($)"](a), 1) == 7988.6
    assert round(STATS["top 10% share of spend"](a), 3) == 0.366
    assert round(STATS["Gini of spend"](a), 3) == 0.533
    assert int(df["lapsed"].sum()) == 356
    assert round(STATS["active share, Apr-Oct 2022"](a), 3) == 0.724
    assert round(STATS["Jan-Oct spend per account, 2022 / 2018"](a), 2) == 2.10
    assert int(a["reactivations"].sum()) == 7531 and int(a["dormant_months"].sum()) == 34930
    assert round(STATS["share of accounts: frequent big spenders"](a), 3) == 0.405
    assert round(STATS["share of 12-month spend: frequent big spenders"](a), 3) == 0.800
    counts = df["event_group"].value_counts()
    assert 795 <= counts["moved_only"] <= 808 and 334 <= counts["lost_job_only"] <= 347
    assert 3371 <= counts["none"] <= 3384
