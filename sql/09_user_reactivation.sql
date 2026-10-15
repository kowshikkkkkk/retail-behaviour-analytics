-- Per-account reactivation counts (same rule as 05_reactivation.sql; __GAP__ filled in by Python).
-- Used for bootstrapping the pooled reactivation rate by resampling accounts.
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
grid AS (
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
)
SELECT user_id,
       SUM(CASE WHEN recent_active = 0 AND earlier_active > 0 THEN 1 ELSE 0 END)                AS dormant_months,
       SUM(CASE WHEN recent_active = 0 AND earlier_active > 0 AND active = 1 THEN 1 ELSE 0 END) AS reactivations
FROM flags
GROUP BY user_id
ORDER BY user_id;
