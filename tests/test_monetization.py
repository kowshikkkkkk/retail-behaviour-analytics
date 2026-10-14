import os
import pathlib
import duckdb
import numpy as np
import pandas as pd
import pytest
from src.monetization import (gini, top_share, share_of_accounts_for_half, concentration,
                              run_category_mix)
from src.sql_metrics import SQL_DIR

EMPTY_SURVEY = pd.DataFrame({"user_id": pd.Series(dtype="string"),
                             "shopping_freq": pd.Series(dtype="string"),
                             "age_group": pd.Series(dtype="string")})


def con_for(rows, cols):
    p = pd.DataFrame(rows, columns=cols)
    con = duckdb.connect()
    con.register("purchases", p)
    con.register("survey_min", EMPTY_SURVEY)
    return con


def test_gini_known_values():
    assert gini([5, 5, 5, 5]) == pytest.approx(0.0)
    assert gini([0, 0, 0, 10]) == pytest.approx(0.75)        # (n-1)/n when one account has everything
    assert gini([1, 2, 3, 4]) == pytest.approx(0.25)


def test_concentration_known_values():
    x = list(range(1, 21))                                   # 20 accounts spending 1..20, total 210
    assert top_share(x, 0.10) == pytest.approx(39 / 210)      # top 2 accounts: 20 + 19
    assert top_share(x, 0.01) == pytest.approx(20 / 210)      # at least one account
    assert share_of_accounts_for_half(x) == pytest.approx(6 / 20)   # 20+19+18+17+16+15 = 105 = half
    c = concentration(x)
    assert c["accounts"] == 20 and c["total_spend"] == 210 and c["median"] == pytest.approx(10.5)


def cat_rows():
    cols = ["user_id", "spend", "qty", "category_clean", "is_gift"]
    rows = [("u1", 60.0, 1, "A", False), ("u2", 40.0, 1, "A", False),
            ("u1", 50.0, 1, "B", False), ("u3", 30.0, 1, "B", False),
            ("u4", 20.0, 1, "C", False), ("u5", 10.0, 1, "D", False),
            ("u1", 15.0, 1, "Unknown", False), ("u2", 25.0, 1, "Sensitive (not broken out)", False),
            ("u6", 999.0, 1, "A", True)]                     # gift card: excluded
    return rows, cols


def test_category_mix_groups_and_shares():
    rows, cols = cat_rows()
    out = run_category_mix(con_for(rows, cols), top_n=2, min_accounts=1)
    assert list(out["category_group"]) == ["A", "B", "Other categories",
                                           "Sensitive (not broken out)", "Unknown"]
    assert list(out["spend"]) == pytest.approx([100, 80, 30, 25, 15])
    assert list(out["share_of_spend"]) == pytest.approx([0.40, 0.32, 0.12, 0.10, 0.06])
    assert list(out["accounts"]) == [2, 2, 2, 1, 1]          # "Other" counts u4 and u5 once each
    assert out["share_of_spend"].sum() == pytest.approx(1.0)


def test_category_mix_suppresses_small_groups():
    rows, cols = cat_rows()
    out = run_category_mix(con_for(rows, cols), top_n=2, min_accounts=2)
    assert list(out["category_group"]) == ["A", "B", "Other categories"]


def test_spend_by_year_uses_jan_oct_only():
    cols = ["user_id", "date", "spend", "is_gift"]
    rows = [("u1", "2019-03-05", 10.0, False), ("u2", "2019-11-05", 100.0, False),
            ("u2", "2020-02-05", 20.0, False), ("u3", "2020-05-05", 50.0, True)]
    p = pd.DataFrame(rows, columns=cols)
    p["date"] = pd.to_datetime(p["date"])
    con = duckdb.connect()
    con.register("purchases", p)
    out = con.execute((SQL_DIR / "07_spend_by_year.sql").read_text()).df().set_index("year")
    assert out.loc[2019, "spend_jan_oct"] == 10 and out.loc[2019, "active_accounts"] == 1
    assert out.loc[2019, "spend_per_account"] == pytest.approx(5.0)         # denominator: 2 accounts
    assert out.loc[2020, "spend_jan_oct"] == 20
    assert out.loc[2020, "spend_per_active_account"] == pytest.approx(20.0)


PARQUET = pathlib.Path("data/processed/purchases_clean.parquet")


@pytest.mark.skipif(os.environ.get("RUN_REAL_DATA") != "1" or not PARQUET.exists(),
                    reason="needs the real cleaned parquet; set RUN_REAL_DATA=1")
def test_real_data_monetization_matches_earlier_numbers():
    from src.sql_metrics import connect, run
    con = connect()
    users = run(con, "02_user_metrics.sql")
    c = concentration(users["spend"])
    assert c["accounts"] == 5014
    assert round(c["total_spend"]) == 40055052
    assert round(c["max"], 1) == 106886.9
    assert 0 < c["gini"] < 1
    cat = run_category_mix(con, min_accounts=1)
    assert round(cat["spend"].sum()) == 40055052
    assert cat["share_of_spend"].sum() == pytest.approx(1.0)
    yr = run(con, "07_spend_by_year.sql")
    assert len(yr) == 5
