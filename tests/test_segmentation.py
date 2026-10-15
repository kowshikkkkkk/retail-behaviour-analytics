import os
import pathlib
import duckdb
import pandas as pd
import pytest
from src.segmentation import (run_rfm, compare_segments, stability, profile, ORDER)

EMPTY_SURVEY = pd.DataFrame({"user_id": pd.Series(dtype="string"),
                             "shopping_freq": pd.Series(dtype="string"),
                             "age_group": pd.Series(dtype="string")})


def con_for(rows):
    p = pd.DataFrame(rows, columns=["user_id", "date", "spend", "is_gift"])
    p["date"] = pd.to_datetime(p["date"])
    con = duckdb.connect()
    con.register("purchases", p)
    con.register("survey_min", EMPTY_SURVEY)
    return con


def series(user, dates, spend):
    return [(user, str(d.date()), spend, False) for d in pd.to_datetime(list(dates))]


def test_hand_checked_segments():
    rows = []
    long_dates = pd.date_range("2022-02-01", periods=10, freq="25D")      # last = 2022-09-13
    rows += series("a", long_dates, 10.0)        # 10 order-days, $100  -> frequent, light
    rows += series("b", long_dates, 50.0)        # 10 order-days, $500  -> frequent, big
    rows += series("c", ["2022-09-01", "2022-10-01"], 10.0)     # 2 order-days, $20   -> occasional, light
    rows += series("d", ["2022-09-01", "2022-10-01"], 100.0)    # 2 order-days, $200  -> occasional, big
    rows += series("e", ["2022-02-01"], 50.0)                   # last purchase 272 days ago -> lapsed
    rows += series("f", ["2020-01-01"], 50.0)                   # 1,034 days ago, nothing in 12 months -> lapsed
    rows += series("g", ["2022-11-15"], 50.0)                   # only after the reference date -> not included
    rows += [("c", "2022-10-25", 999.0, True)]                  # gift card: ignored
    seg = run_rfm(con_for(rows), "2022-10-31").set_index("user_id")
    assert set(seg.index) == {"a", "b", "c", "d", "e", "f"}
    assert seg.loc["a", "segment"] == "Frequent light spenders"
    assert seg.loc["b", "segment"] == "Frequent big spenders"
    assert seg.loc["c", "segment"] == "Occasional light spenders"
    assert seg.loc["d", "segment"] == "Occasional big spenders"
    assert seg.loc["e", "segment"] == "Lapsed" and seg.loc["f", "segment"] == "Lapsed"
    assert seg.loc["c", "recency_days"] == 30                   # gift card on 10-25 does not count
    assert seg.loc["a", "frequency_12m"] == 10 and seg.loc["b", "monetary_12m"] == pytest.approx(500.0)
    assert seg.loc["a", "f_med"] == 6 and seg.loc["a", "m_med"] == pytest.approx(150.0)
    assert seg.loc["f", "frequency_12m"] == 0


def test_lapsed_boundary_is_180_days():
    rows = series("h", ["2022-05-04"], 40.0) + series("i", ["2022-05-03"], 40.0)   # 180 vs 181 days
    seg = run_rfm(con_for(rows), "2022-10-31").set_index("user_id")
    assert seg.loc["h", "recency_days"] == 180 and seg.loc["h", "segment"] != "Lapsed"
    assert seg.loc["i", "recency_days"] == 181 and seg.loc["i", "segment"] == "Lapsed"


def test_stability_kappa_hand_checked():
    merged = pd.DataFrame({"user_id": list("wxyz"),
                           "segment_prev": ["A", "A", "B", "B"],
                           "segment_now": ["A", "B", "B", "B"]})
    s, trans = stability(merged)
    assert s["observed_agreement"] == pytest.approx(0.75)
    assert s["chance_agreement"] == pytest.approx(0.5)          # 0.5*0.25 + 0.5*0.75
    assert s["kappa"] == pytest.approx(0.5)
    assert trans.loc["A", "A"] == pytest.approx(0.5) and trans.loc["B", "B"] == pytest.approx(1.0)


def test_compare_segments_keeps_only_accounts_in_both():
    prev = pd.DataFrame({"user_id": ["u1", "u2"], "segment": ["A", "B"]})
    now = pd.DataFrame({"user_id": ["u2", "u3"], "segment": ["B", "A"]})
    m = compare_segments(prev, now)
    assert list(m["user_id"]) == ["u2"]


def test_profile_ratio_and_small_cell_suppression():
    seg = pd.DataFrame({"user_id": [f"u{i}" for i in range(1, 7)],
                        "segment": ["X", "X", "X", "Y", "Y", "Y"]})
    sv = pd.DataFrame({"user_id": [f"u{i}" for i in range(1, 7)],
                       "age_group": ["A", "A", "B", "B", "B", "A"]})
    full = profile(seg, sv, "age_group", min_cell=1).set_index(["segment", "level"])
    assert full.loc[("X", "A"), "ratio"] == pytest.approx((2 / 3) / 0.5)
    assert full.loc[("X", "B"), "ratio"] == pytest.approx((1 / 3) / 0.5)
    small = profile(seg, sv, "age_group", min_cell=2)
    assert set(zip(small["segment"], small["level"])) == {("X", "A"), ("Y", "B")}


PARQUET = pathlib.Path("data/processed/purchases_clean.parquet")


@pytest.mark.skipif(os.environ.get("RUN_REAL_DATA") != "1" or not PARQUET.exists(),
                    reason="needs the real cleaned parquet; set RUN_REAL_DATA=1")
def test_real_data_segments():
    from src.sql_metrics import connect
    con = connect()
    now = run_rfm(con, "2022-10-31")
    prev = run_rfm(con, "2021-10-31")
    assert len(now) == 5014 and set(now["segment"]) <= set(ORDER)
    assert 4800 < len(prev) < 5014
    stab, _ = stability(compare_segments(prev, now))
    assert 0 < stab["kappa"] < 1
