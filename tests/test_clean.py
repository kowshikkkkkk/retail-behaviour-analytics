import os
import pathlib
import pandas as pd
import pytest
from src.clean import (apply_window, flag_gift_cards, flag_duplicates, add_category_clean,
                       clean, SENSITIVE_LABEL, UNKNOWN_LABEL)


def make(rows):
    df = pd.DataFrame(rows, columns=["order_date", "price", "qty", "state", "title",
                                     "asin", "category", "user_id"])
    for c in ["state", "title", "asin", "category", "user_id"]:
        df[c] = df[c].astype("string")
    df["date"] = pd.to_datetime(df["order_date"], format="%Y-%m-%d")
    df["spend"] = df["price"] * df["qty"]
    return df


def row(d="2020-05-01", price=10.0, qty=1.0, title="Thing", cat="HEADPHONES", user="u1",
        state="NJ", asin="A1"):
    return [d, price, qty, state, title, asin, cat, user]


def test_window_keeps_boundaries_and_drops_outside():
    df = make([row("2017-12-31"), row("2018-01-01"), row("2022-10-31"), row("2022-11-01"),
               row("2024-08-15")])
    out = apply_window(df)
    assert list(out["order_date"]) == ["2018-01-01", "2022-10-31"]


def test_gift_detection():
    df = make([row(cat="GIFT_CARD"), row(cat="GIFT_XXRD"), row(cat="ELECTRONIC_GIFT_XXRD"),
               row(cat="HEADPHONES", title="$10 Xbox Gift Card [Digital Code]"),
               row(cat="GIFT_WRAP"), row(cat="GIFTS_AND_OCCASIONS"),
               row(cat=None, title=None)])
    flags = list(flag_gift_cards(df)["is_gift"])
    assert flags == [True, True, True, True, False, False, False]


def test_duplicates_are_flagged_not_removed():
    df = make([row(), row(), row(price=11.0)])
    out = flag_duplicates(df)
    assert len(out) == 3
    assert list(out["is_exact_dup"]) == [False, True, False]


def test_duplicate_detection_handles_missing_values():
    df = make([row(cat=None, title=None), row(cat=None, title=None)])
    assert list(flag_duplicates(df)["is_exact_dup"]) == [False, True]


def test_category_clean():
    df = make([row(cat=None), row(cat="MEDICATION"), row(cat="CONDOM"), row(cat="HEADPHONES"),
               row(cat="NUTRITIONAL_SUPPLEMENT")])
    out = list(add_category_clean(df)["category_clean"])
    assert out == [UNKNOWN_LABEL, SENSITIVE_LABEL, SENSITIVE_LABEL, "HEADPHONES",
                   "NUTRITIONAL_SUPPLEMENT"]


def test_clean_only_window_deletes_and_log_adds_up():
    df = make([row("2017-12-31", price=5), row("2019-01-01", price=10, cat="GIFT_CARD"),
               row("2019-01-02", price=20), row("2019-01-02", price=20),
               row("2022-11-05", price=7)])
    out, log = clean(df)
    assert len(out) == 3                                   # only 2 rows outside window removed
    win = log[log["step"].str.startswith("window")].iloc[0]
    assert win["rows_affected"] == 2 and win["spend_affected"] == 12.0
    assert out["is_gift"].sum() == 1 and out["is_exact_dup"].sum() == 1
    assert out["spend"].sum() == 50.0                      # nothing else was dropped
    assert "month" in out.columns and out["month"].iloc[0] == pd.Timestamp("2019-01-01")


REAL = pathlib.Path("data/raw/amazon-purchases.csv")


@pytest.mark.skipif(os.environ.get("RUN_REAL_DATA") != "1" or not REAL.exists(),
                    reason="slow; set RUN_REAL_DATA=1 to check against the real file")
def test_real_data_matches_audit_numbers():
    from src.load import load_purchases
    out, _ = clean(load_purchases())
    base = out[~out["is_gift"]]
    assert len(out) == 1737058
    assert len(base) == 1698208
    assert int(base["is_exact_dup"].sum()) == 4969
    assert round(out["spend"].sum()) == 41258954
    assert round(base["spend"].sum()) == 40055052
