-- Per-account features for the bootstrap. One row per account in the base table (zeros kept).
-- Jan-Oct spend in 2018 and 2022 (same months), and months active in Apr-Oct 2022 (max 7).
WITH base AS (
    SELECT user_id, date, spend FROM purchases WHERE NOT is_gift
),
users AS (
    SELECT DISTINCT user_id FROM base
)
SELECT u.user_id,
       COALESCE(SUM(b.spend) FILTER (WHERE EXTRACT(year FROM b.date) = 2018
                                       AND EXTRACT(month FROM b.date) <= 10), 0) AS spend_2018_jan_oct,
       COALESCE(SUM(b.spend) FILTER (WHERE EXTRACT(year FROM b.date) = 2022
                                       AND EXTRACT(month FROM b.date) <= 10), 0) AS spend_2022_jan_oct,
       COUNT(DISTINCT DATE_TRUNC('month', b.date))
           FILTER (WHERE EXTRACT(year FROM b.date) = 2022
                     AND EXTRACT(month FROM b.date) BETWEEN 4 AND 10)            AS active_months_apr_oct_2022
FROM users u
LEFT JOIN base b ON b.user_id = u.user_id
GROUP BY u.user_id
ORDER BY u.user_id;
