import os
import pathlib
import duckdb
import pandas as pd
import pytest
from src.sql_metrics import SQL_DIR

EMPTY_SURVEY = pd.DataFrame({"user_id": pd.Series(dtype="string"),
                             "shopping_freq": pd.Series(dtype="string"),
                             "age_group": pd.Series(dtype="string")})


def run_sql(purchases, survey, name):
    con = duckdb.connect()
    con.register("purchases", purchases)
    con.register("survey_min", survey)
    return con.execute((SQL_DIR / name).read_text()).df()


def make_purchases(rows):
    df = pd.DataFrame(rows, columns=["user_id", "date", "qty", "spend", "is_gift"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def small_data():
    # u1: two lines on one day (= 1 order); a gift card in Feb (excluded)
    # u2: an exact duplicate row on 2019-03-11 (kept: same day = same order, 2 lines)
    # u3: only a gift card -> not in the base table at all
    return make_purchases([
        ("u1", "2019-01-05", 1, 10.0, False), ("u1", "2019-01-05", 2, 20.0, False),
        ("u1", "2019-02-01", 1, 50.0, True),  ("u1", "2019-03-10", 1, 5.0, False),
        ("u2", "2019-01-20", 1, 40.0, False),
        ("u2", "2019-03-11", 1, 15.0, False), ("u2", "2019-03-11", 1, 15.0, False),
        ("u3", "2019-01-01", 1, 25.0, True),
    ])


def test_monthly_matches_pandas_and_shows_gap_month():
    p = small_data()
    out = run_sql(p, EMPTY_SURVEY, "01_monthly_activity.sql")
    base = p[~p["is_gift"]]
    orders = base.groupby(["user_id", "date"]).agg(lines=("spend", "size"), units=("qty", "sum"),
                                                   spend=("spend", "sum")).reset_index()
    orders["month"] = orders["date"].dt.to_period("M").dt.to_timestamp()
    exp = orders.groupby("month").agg(active=("user_id", "nunique"), orders=("date", "size"),
                                      lines=("lines", "sum"), units=("units", "sum"),
                                      spend=("spend", "sum"))
    assert list(out["month"]) == [pd.Timestamp("2019-01-01"), pd.Timestamp("2019-02-01"),
                                  pd.Timestamp("2019-03-01")]          # Feb is present with zeros
    for m in exp.index:
        r = out[out["month"] == m].iloc[0]
        assert r["active_users"] == exp.loc[m, "active"]
        assert r["orders"] == exp.loc[m, "orders"]
        assert r["line_items"] == exp.loc[m, "lines"]
        assert r["units"] == exp.loc[m, "units"]
        assert r["spend"] == pytest.approx(exp.loc[m, "spend"])
    feb = out[out["month"] == pd.Timestamp("2019-02-01")].iloc[0]
    assert feb["active_users"] == 0 and feb["orders"] == 0
    assert list(out["active_share"]) == pytest.approx([1.0, 0.0, 1.0])  # denominator = 2 (u3 excluded)
    assert list(out["active_share_3m_avg"]) == pytest.approx([1.0, 0.5, 2 / 3])
    assert out["active_users_change"].tolist()[1:] == [-2, 2]


def test_user_metrics():
    out = run_sql(small_data(), EMPTY_SURVEY, "02_user_metrics.sql").set_index("user_id")
    assert set(out.index) == {"u1", "u2"}
    assert out.loc["u1", "order_days"] == 2 and out.loc["u1", "line_items"] == 3
    assert out.loc["u1", "spend"] == pytest.approx(35.0)
    assert out.loc["u2", "order_days"] == 2 and out.loc["u2", "spend"] == pytest.approx(70.0)
    assert out.loc["u1", "median_days_between_orders"] == 64     # 2019-01-05 -> 2019-03-10
    assert out.loc["u2", "median_days_between_orders"] == 50     # 2019-01-20 -> 2019-03-11
    assert out.loc["u2", "spend_decile"] == 1 and out.loc["u1", "spend_decile"] == 2
    assert out.loc["u1", "active_months"] == 2


def test_frequency_query_joins_and_suppresses_small_groups():
    rows, survey = [], []
    for i in range(75):
        uid = f"u{i}"
        rows.append((uid, "2019-06-01", 1, (i + 1) * 10.0, False))
        survey.append((uid, "A" if i < 35 else ("B" if i < 70 else "C"), "25 - 34 years"))
    p = make_purchases(rows)
    s = pd.DataFrame(survey, columns=["user_id", "shopping_freq", "age_group"])
    out = run_sql(p, s, "03_spend_by_shopping_frequency.sql").set_index("shopping_freq")
    assert set(out.index) == {"A", "B"}                          # C has 5 accounts -> suppressed
    base = p.merge(s, on="user_id")
    for g in ["A", "B"]:
        sp = base[base["shopping_freq"] == g]["spend"]
        assert out.loc[g, "accounts"] == len(sp)
        assert out.loc[g, "median_spend"] == pytest.approx(sp.median())
        assert out.loc[g, "mean_spend"] == pytest.approx(round(sp.mean()))


PARQUET = pathlib.Path("data/processed/purchases_clean.parquet")


@pytest.mark.skipif(os.environ.get("RUN_REAL_DATA") != "1" or not PARQUET.exists(),
                    reason="needs the real cleaned parquet; set RUN_REAL_DATA=1")
def test_real_data_sql_matches_audit():
    from src.sql_metrics import connect, run
    con = connect()
    monthly = run(con, "01_monthly_activity.sql")
    users = run(con, "02_user_metrics.sql")
    assert len(monthly) == 58
    assert len(users) == 5014
    assert round(monthly["spend"].sum()) == 40055052
    assert round(users["spend"].sum()) == 40055052
    assert monthly["active_share"].between(0, 1).all()
