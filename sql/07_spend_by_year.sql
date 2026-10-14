-- Same months every year (Jan-Oct), because Nov-Dec 2022 are incomplete.
-- Base = analysis window, gift cards excluded. Denominator = all accounts in the base table.
WITH base AS (
    SELECT user_id, date, spend
    FROM purchases
    WHERE NOT is_gift
),
n AS (
    SELECT COUNT(DISTINCT user_id) AS n_accounts FROM base
)
SELECT EXTRACT(year FROM b.date)                      AS year,
       SUM(b.spend)                                   AS spend_jan_oct,
       COUNT(DISTINCT b.user_id)                      AS active_accounts,
       SUM(b.spend) / MAX(n.n_accounts)               AS spend_per_account,
       SUM(b.spend) / COUNT(DISTINCT b.user_id)       AS spend_per_active_account
FROM base b
CROSS JOIN n
WHERE EXTRACT(month FROM b.date) <= 10
GROUP BY 1
ORDER BY 1;
