-- Pool for the A/B SIMULATION: every real dormant account-month (3 quiet months before, bought before that).
-- bought = 1 if the account bought in that month. spend_in_month = its gift-card-free spend that month.
-- __GAP__ and __GAP_PLUS_1__ are filled in by Python (default 3).
WITH base AS (
    SELECT user_id, DATE_TRUNC('month', date) AS month, SUM(spend) AS spend
    FROM purchases
    WHERE NOT is_gift
    GROUP BY user_id, DATE_TRUNC('month', date)
),
bounds AS (
    SELECT MIN(month) AS lo, MAX(month) AS hi FROM base
),
months AS (
    SELECT UNNEST(generate_series(lo, hi, INTERVAL 1 MONTH)) AS month FROM bounds
),
users AS (
    SELECT DISTINCT user_id FROM base
),
grid AS (
    SELECT u.user_id, m.month,
           CASE WHEN b.user_id IS NULL THEN 0 ELSE 1 END AS active,
           COALESCE(b.spend, 0) AS spend
    FROM users u
    CROSS JOIN months m
    LEFT JOIN base b ON b.user_id = u.user_id AND b.month = m.month
),
flags AS (
    SELECT user_id, month, active, spend,
           COALESCE(SUM(active) OVER (PARTITION BY user_id ORDER BY month
                ROWS BETWEEN __GAP__ PRECEDING AND 1 PRECEDING), 0)           AS recent_active,
           COALESCE(SUM(active) OVER (PARTITION BY user_id ORDER BY month
                ROWS BETWEEN UNBOUNDED PRECEDING AND __GAP_PLUS_1__ PRECEDING), 0) AS earlier_active
    FROM grid
)
SELECT month, active AS bought, spend AS spend_in_month
FROM flags
WHERE recent_active = 0 AND earlier_active > 0
ORDER BY month, user_id;
