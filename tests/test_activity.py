import os
import pathlib
import duckdb
import numpy as np
import pandas as pd
import pytest
from src.sql_metrics import SQL_DIR
from src.activity import run_gap

EMPTY_SURVEY = pd.DataFrame({"user_id": pd.Series(dtype="string"),
                             "shopping_freq": pd.Series(dtype="string"),
                             "age_group": pd.Series(dtype="string")})


def con_for(rows):
    p = pd.DataFrame(rows, columns=["user_id", "date", "qty", "spend", "is_gift"])
    p["date"] = pd.to_datetime(p["date"])
    con = duckdb.connect()
    con.register("purchases", p)
    con.register("survey_min", EMPTY_SURVEY)
    return con


def brute_reactivation(purchases, gap):
    """Independent pandas/numpy version, loop by loop, to cross-check the SQL window frames."""
    base = purchases[~purchases["is_gift"]].copy()
    base["month"] = base["date"].dt.to_period("M").dt.to_timestamp()
    months = pd.date_range(base["month"].min(), base["month"].max(), freq="MS")
    act = (base.drop_duplicates(["user_id", "month"]).assign(a=1)
           .pivot(index="user_id", columns="month", values="a")
           .reindex(columns=months).fillna(0).to_numpy())
    dormant = np.zeros(len(months), dtype=int)
    react = np.zeros(len(months), dtype=int)
    for row in act:
        for i in range(len(months)):
            recent = row[max(0, i - gap):i].sum()
            earlier = row[:max(0, i - gap)].sum()
            if recent == 0 and earlier > 0:
                dormant[i] += 1
                react[i] += int(row[i] == 1)
    return pd.DataFrame({"month": months, "dormant_accounts": dormant, "reactivated": react})


def reactivation_rows():
    # u1: Jan, Jun       (quiet Feb-May: reactivates in Jun under gap 2, 3 and 4)
    # u2: Jan, Feb, May  (quiet Mar-Apr: reactivates in May under gap 2 only)
    # u3: first purchase in Jun (new, not a reactivation), gift card in Mar (ignored)
    # u4: Jan, Oct       (quiet Feb-Sep: reactivates in Oct)
    r = []
    for u, ds in {"u1": ["2019-01-10", "2019-06-10"], "u2": ["2019-01-05", "2019-02-05", "2019-05-05"],
                  "u3": ["2019-06-20"], "u4": ["2019-01-15", "2019-10-15"]}.items():
        r += [(u, d, 1, 10.0, False) for d in ds]
    r.append(("u3", "2019-03-01", 1, 25.0, True))
    return r


def test_reactivation_hand_checked_events():
    con = con_for(reactivation_rows())
    g3 = run_gap(con, 3).set_index("month")
    assert g3["reactivated"].sum() == 2
    assert g3.loc[pd.Timestamp("2019-06-01"), "reactivated"] == 1       # u1
    assert g3.loc[pd.Timestamp("2019-10-01"), "reactivated"] == 1       # u4
    assert g3.loc[pd.Timestamp("2019-05-01"), "reactivated"] == 0       # u2 not dormant for 3 months
    assert run_gap(con, 2).set_index("month").loc[pd.Timestamp("2019-05-01"), "reactivated"] == 1
    assert run_gap(con, 4)["reactivated"].sum() == 2


@pytest.mark.parametrize("gap", [2, 3, 4])
def test_reactivation_sql_matches_brute_force(gap):
    rows = reactivation_rows()
    con = con_for(rows)
    sql = run_gap(con, gap)
    p = pd.DataFrame(rows, columns=["user_id", "date", "qty", "spend", "is_gift"])
    p["date"] = pd.to_datetime(p["date"])
    exp = brute_reactivation(p, gap)
    assert list(sql["month"]) == list(exp["month"])
    assert list(sql["dormant_accounts"]) == list(exp["dormant_accounts"])
    assert list(sql["reactivated"]) == list(exp["reactivated"])


def test_established_activity():
    # window starts Jan 2019. Established = bought in Jan-Mar: u1, u2. u3 starts in Apr (not established).
    rows = [("u1", "2019-01-10", 1, 5.0, False), ("u1", "2019-04-10", 1, 5.0, False),
            ("u1", "2019-05-10", 1, 5.0, False),
            ("u2", "2019-03-10", 1, 5.0, False), ("u2", "2019-05-11", 1, 5.0, False),
            ("u2", "2019-06-11", 1, 99.0, True),                 # gift card only in Jun: not active
            ("u3", "2019-04-12", 1, 5.0, False), ("u3", "2019-06-12", 1, 5.0, False)]
    out = con_for(rows).execute((SQL_DIR / "04_established_activity.sql").read_text()).df()
    assert list(out["month"]) == [pd.Timestamp("2019-04-01"), pd.Timestamp("2019-05-01"),
                                  pd.Timestamp("2019-06-01")]
    assert (out["n_established"] == 2).all()
    assert list(out["active_share_established"]) == pytest.approx([0.5, 1.0, 0.0])
    assert list(out["active_share_3m_avg"]) == pytest.approx([0.5, 0.75, 0.5])


PARQUET = pathlib.Path("data/processed/purchases_clean.parquet")


@pytest.mark.skipif(os.environ.get("RUN_REAL_DATA") != "1" or not PARQUET.exists(),
                    reason="needs the real cleaned parquet; set RUN_REAL_DATA=1")
def test_real_data_reactivation_and_established():
    from src.sql_metrics import connect, run
    con = connect()
    p = con.execute("SELECT user_id, date, qty, spend, is_gift FROM purchases").df()
    for gap in (2, 3, 4):
        sql = run_gap(con, gap)
        exp = brute_reactivation(p, gap)
        assert list(sql["dormant_accounts"]) == list(exp["dormant_accounts"])
        assert list(sql["reactivated"]) == list(exp["reactivated"])
    est = run(con, "04_established_activity.sql")
    assert len(est) == 55
    assert est["active_share_established"].between(0, 1).all()
