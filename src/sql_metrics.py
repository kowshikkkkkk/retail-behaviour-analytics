"""Run the DuckDB SQL files. Views: purchases (cleaned parquet) and survey_min (3 safe columns)."""
import pathlib
import duckdb

ROOT = pathlib.Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"
PARQUET = "data/processed/purchases_clean.parquet"
SURVEY = "data/raw/survey.csv"


def connect():
    con = duckdb.connect()
    con.execute(f"CREATE VIEW purchases AS SELECT * FROM read_parquet('{PARQUET}')")
    # Only non-sensitive columns are ever selected from the survey.
    con.execute(
        'CREATE VIEW survey_min AS SELECT "Survey ResponseID" AS user_id, '
        '"Q-amazon-use-how-oft" AS shopping_freq, "Q-demos-age" AS age_group '
        f"FROM read_csv_auto('{SURVEY}')")
    return con


def run(con, name):
    return con.execute((SQL_DIR / name).read_text()).df()


def main():
    out_tables = pathlib.Path("reports/tables")
    out_tables.mkdir(parents=True, exist_ok=True)
    con = connect()
    monthly = run(con, "01_monthly_activity.sql")
    users = run(con, "02_user_metrics.sql")
    freq = run(con, "03_spend_by_shopping_frequency.sql")
    monthly.to_csv(out_tables / "monthly_activity.csv", index=False)
    freq.to_csv(out_tables / "spend_by_shopping_frequency.csv", index=False)
    users.to_csv("data/processed/user_metrics.csv", index=False)  # has IDs: stays git-ignored
    print("monthly rows:", len(monthly), "| accounts:", len(users))
    show = monthly.assign(month=monthly["month"].dt.strftime("%Y-%m")).round(3)
    print(show.head(3).to_string(index=False))
    print(show.tail(3).to_string(index=False))
    print("\nspend by shopping frequency (descriptive only):")
    print(freq.to_string(index=False))
    print("\nuser table summary:")
    print(users[["order_days", "spend", "median_days_between_orders"]].describe().round(1).to_string())


if __name__ == "__main__":
    main()
