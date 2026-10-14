-- Monthly activity. Base = analysis window, gift cards excluded, duplicates kept.
-- "Order" is a proxy: one account's purchases on one calendar day (no order ID in the data).
-- A month with no purchases still gets a row (zeros), so gaps are visible.
WITH base AS (
    SELECT user_id, date, qty, spend
    FROM purchases
    WHERE NOT is_gift
),
orders AS (                                   -- one row per account per day
    SELECT user_id, date,
           COUNT(*)   AS line_items,
           SUM(qty)   AS units,
           SUM(spend) AS spend
    FROM base
    GROUP BY user_id, date
),
denominator AS (                              -- fixed denominator for active share
    SELECT COUNT(DISTINCT user_id) AS n_users FROM base
),
bounds AS (
    SELECT MIN(DATE_TRUNC('month', date)) AS lo, MAX(DATE_TRUNC('month', date)) AS hi FROM base
),
months AS (
    SELECT UNNEST(generate_series(lo, hi, INTERVAL 1 MONTH)) AS month FROM bounds
),
monthly AS (
    SELECT DATE_TRUNC('month', date) AS month,
           COUNT(DISTINCT user_id) AS active_users,
           COUNT(*)                AS orders,
           SUM(line_items)         AS line_items,
           SUM(units)              AS units,
           SUM(spend)              AS spend
    FROM orders
    GROUP BY 1
),
filled AS (
    SELECT m.month,
           COALESCE(x.active_users, 0) AS active_users,
           COALESCE(x.orders, 0)       AS orders,
           COALESCE(x.line_items, 0)   AS line_items,
           COALESCE(x.units, 0)        AS units,
           COALESCE(x.spend, 0)        AS spend
    FROM months m
    LEFT JOIN monthly x ON x.month = m.month
)
SELECT f.month,
       f.active_users,
       f.active_users * 1.0 / d.n_users AS active_share,
       AVG(f.active_users * 1.0 / d.n_users)
           OVER (ORDER BY f.month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS active_share_3m_avg,
       f.active_users - LAG(f.active_users) OVER (ORDER BY f.month)         AS active_users_change,
       f.orders, f.line_items, f.units, f.spend,
       f.spend / NULLIF(f.orders, 0)         AS spend_per_order,
       f.line_items * 1.0 / NULLIF(f.orders, 0) AS items_per_order
FROM filled f
CROSS JOIN denominator d
ORDER BY f.month;
