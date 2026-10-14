"""Shared loader and analysis window."""
import pathlib
import pandas as pd

RAW = pathlib.Path("data/raw")
WINDOW_START = pd.Timestamp("2018-01-01")
WINDOW_END = pd.Timestamp("2022-10-31")
COLS = ["order_date", "price", "qty", "state", "title", "asin", "category", "user_id"]

def load_purchases():
    df = pd.read_csv(
        RAW / "amazon-purchases.csv", encoding="utf-8",
        dtype={"Shipping Address State": "string", "Title": "string",
               "ASIN/ISBN (Product Code)": "string", "Category": "string",
               "Survey ResponseID": "string"})
    df.columns = COLS
    df["date"] = pd.to_datetime(df["order_date"], format="%Y-%m-%d")
    df["spend"] = df["price"] * df["qty"]
    return df
