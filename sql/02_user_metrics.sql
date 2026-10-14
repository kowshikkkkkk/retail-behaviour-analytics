-- One row per account: spend, order-days, activity, gaps between orders, spend decile.
-- Base = analysis window, gift cards excluded, duplicates kept.
WITH base AS (
    SELECT user_id, date, spend
    FROM purchases
    WHERE NOT is_gift
),
orders AS (
    SELECT user_id, date, COUNT(*) AS line_items, SUM(spend) AS spend
    FROM base
    GROUP BY user_id, date
),
n_months AS (                                 -- months present in the base table (58 in the real data)
    SELECT COUNT(DISTINCT DATE_TRUNC('month', date)) AS n FROM base
),
gaps AS (
    SELECT user_id,
           DATE_DIFF('day', LAG(date) OVER (PARTITION BY user_id ORDER BY date), date) AS days_since_prev
    FROM orders
),
gap_stats AS (
    SELECT user_id, MEDIAN(days_since_prev) AS median_days_between_orders
    FROM gaps
    WHERE days_since_prev IS NOT NULL
    GROUP BY user_id
),
per_user AS (
    SELECT user_id,
           COUNT(*)        AS order_days,
           SUM(line_items) AS line_items,
           SUM(spend)      AS spend,
           COUNT(DISTINCT DATE_TRUNC('month', date)) AS active_months,
           MIN(date)       AS first_seen_in_window,
           MAX(date)       AS last_seen_in_window
    FROM orders
    GROUP BY user_id
)
SELECT p.user_id, p.order_days, p.line_items, p.spend, p.active_months,
       p.first_seen_in_window, p.last_seen_in_window,
       g.median_days_between_orders,
       p.order_days * 1.0 / n.n          AS order_days_per_month,
       p.spend / p.order_days            AS spend_per_order,
       NTILE(10) OVER (ORDER BY p.spend DESC) AS spend_decile   -- 1 = top 10% of accounts
FROM per_user p
CROSS JOIN n_months n
LEFT JOIN gap_stats g ON g.user_id = p.user_id
ORDER BY p.spend DESC;
