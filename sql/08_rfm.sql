-- RFM segments as of __REF_DATE__ (filled in by Python). Base = gift cards excluded, duplicates kept.
-- Recency  = days since the account's last purchase on or before the reference date.
-- Frequency = order-days in the 365 days up to the reference date (order-day = one account, one day).
-- Monetary  = spend in the same 365 days.
-- Rules, in order:
--   Lapsed                     : no purchase in the last 180 days
--   among the rest, "frequent" = frequency at or above the median of non-lapsed accounts,
--                  "big"       = spend at or above the median of non-lapsed accounts
WITH base AS (
    SELECT user_id, CAST(date AS DATE) AS d, spend
    FROM purchases
    WHERE NOT is_gift AND CAST(date AS DATE) <= DATE '__REF_DATE__'
),
orders AS (
    SELECT user_id, d, SUM(spend) AS spend FROM base GROUP BY user_id, d
),
rfm AS (
    SELECT user_id,
           DATE_DIFF('day', MAX(d), DATE '__REF_DATE__')                                  AS recency_days,
           COUNT(*) FILTER (WHERE d > DATE '__REF_DATE__' - 365)                          AS frequency_12m,
           COALESCE(SUM(spend) FILTER (WHERE d > DATE '__REF_DATE__' - 365), 0)           AS monetary_12m
    FROM orders
    GROUP BY user_id
),
cut AS (
    SELECT MEDIAN(frequency_12m) AS f_med, MEDIAN(monetary_12m) AS m_med
    FROM rfm
    WHERE recency_days <= 180
)
SELECT r.user_id, r.recency_days, r.frequency_12m, r.monetary_12m, c.f_med, c.m_med,
       CASE WHEN r.recency_days > 180                                        THEN 'Lapsed'
            WHEN r.frequency_12m >= c.f_med AND r.monetary_12m >= c.m_med    THEN 'Frequent big spenders'
            WHEN r.frequency_12m >= c.f_med                                  THEN 'Frequent light spenders'
            WHEN r.monetary_12m >= c.m_med                                   THEN 'Occasional big spenders'
            ELSE 'Occasional light spenders' END AS segment
FROM rfm r
CROSS JOIN cut c
ORDER BY r.user_id;
