-- Descriptive only: spend per account by the self-reported shopping-frequency answer.
-- Groups under 30 accounts are suppressed.
WITH user_spend AS (
    SELECT user_id, SUM(spend) AS spend, COUNT(DISTINCT date) AS order_days
    FROM purchases
    WHERE NOT is_gift
    GROUP BY user_id
)
SELECT s.shopping_freq,
       COUNT(*)                    AS accounts,
       ROUND(MEDIAN(u.spend), 0)   AS median_spend,
       ROUND(AVG(u.spend), 0)      AS mean_spend,
       ROUND(MEDIAN(u.order_days), 0) AS median_order_days
FROM user_spend u
JOIN survey_min s ON s.user_id = u.user_id
GROUP BY s.shopping_freq
HAVING COUNT(*) >= 30
ORDER BY median_spend;
