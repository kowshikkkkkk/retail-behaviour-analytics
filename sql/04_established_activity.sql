-- "Established" accounts = bought at least once in the first 3 months of the window.
-- Active share is tracked from month 4 onwards (month 1-3 would be 100% by construction).
-- Base = analysis window, gift cards excluded, duplicates kept.
WITH base AS (
    SELECT DISTINCT user_id, DATE_TRUNC('month', date) AS month
    FROM purchases
    WHERE NOT is_gift
),
bounds AS (
    SELECT MIN(month) AS lo, MAX(month) AS hi FROM base
),
established AS (
    SELECT DISTINCT b.user_id
    FROM base b CROSS JOIN bounds s
    WHERE b.month < s.lo + INTERVAL 3 MONTH
),
n AS (
    SELECT COUNT(*) AS n_established FROM established
),
active AS (
    SELECT b.month, COUNT(*) AS active_users
    FROM base b
    JOIN established e ON e.user_id = b.user_id
    GROUP BY b.month
),
months AS (
    SELECT UNNEST(generate_series(lo + INTERVAL 3 MONTH, hi, INTERVAL 1 MONTH)) AS month FROM bounds
)
SELECT m.month,
       COALESCE(a.active_users, 0)                          AS active_users,
       n.n_established,
       COALESCE(a.active_users, 0) * 1.0 / n.n_established  AS active_share_established,
       AVG(COALESCE(a.active_users, 0) * 1.0 / n.n_established)
           OVER (ORDER BY m.month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS active_share_3m_avg
FROM months m
CROSS JOIN n
LEFT JOIN active a ON a.month = m.month
ORDER BY m.month;
