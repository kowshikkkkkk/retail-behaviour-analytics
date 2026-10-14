-- Reactivation. __GAP__ is filled in by Python (default 3).
-- An account is "dormant" at the start of month m if it bought nothing in the previous __GAP__
-- months AND had bought at least once before that quiet stretch.
-- Reactivated in month m = dormant at the start of m and buys in m.
-- Base = analysis window, gift cards excluded. Months before the window are unknown.
WITH base AS (
    SELECT DISTINCT user_id, DATE_TRUNC('month', date) AS month
    FROM purchases
    WHERE NOT is_gift
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
grid AS (                                     -- one row per account per month
    SELECT u.user_id, m.month,
           CASE WHEN b.user_id IS NULL THEN 0 ELSE 1 END AS active
    FROM users u
    CROSS JOIN months m
    LEFT JOIN base b ON b.user_id = u.user_id AND b.month = m.month
),
flags AS (
    SELECT user_id, month, active,
           COALESCE(SUM(active) OVER (PARTITION BY user_id ORDER BY month
                ROWS BETWEEN __GAP__ PRECEDING AND 1 PRECEDING), 0)           AS recent_active,
           COALESCE(SUM(active) OVER (PARTITION BY user_id ORDER BY month
                ROWS BETWEEN UNBOUNDED PRECEDING AND __GAP_PLUS_1__ PRECEDING), 0) AS earlier_active
    FROM grid
),
monthly AS (
    SELECT month,
           SUM(CASE WHEN recent_active = 0 AND earlier_active > 0 THEN 1 ELSE 0 END)             AS dormant_accounts,
           SUM(CASE WHEN recent_active = 0 AND earlier_active > 0 AND active = 1 THEN 1 ELSE 0 END) AS reactivated
    FROM flags
    GROUP BY month
)
SELECT month, dormant_accounts, reactivated,
       reactivated * 1.0 / NULLIF(dormant_accounts, 0) AS reactivation_rate
FROM monthly
ORDER BY month;
