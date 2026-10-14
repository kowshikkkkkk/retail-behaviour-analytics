-- Category mix. Base = analysis window, gift cards excluded.
-- Top __TOP_N__ regular categories by spend are shown by name; the rest are "Other categories".
-- "Sensitive (not broken out)" and "Unknown" always stay as their own buckets.
-- Buckets with fewer than __MIN_ACCOUNTS__ distinct accounts are suppressed.
WITH base AS (
    SELECT user_id, category_clean AS category, spend, qty
    FROM purchases
    WHERE NOT is_gift
),
cat_spend AS (
    SELECT category, SUM(spend) AS spend FROM base GROUP BY category
),
ranked AS (
    SELECT category,
           category IN ('Unknown', 'Sensitive (not broken out)') AS special,
           RANK() OVER (PARTITION BY category IN ('Unknown', 'Sensitive (not broken out)')
                        ORDER BY spend DESC) AS rnk
    FROM cat_spend
),
labelled AS (
    SELECT b.user_id, b.spend, b.qty,
           CASE WHEN r.special THEN b.category
                WHEN r.rnk <= __TOP_N__ THEN b.category
                ELSE 'Other categories' END AS category_group
    FROM base b
    JOIN ranked r ON r.category = b.category
),
tot AS (
    SELECT SUM(spend) AS total FROM labelled
)
SELECT l.category_group,
       SUM(l.spend)                   AS spend,
       SUM(l.spend) / t.total         AS share_of_spend,
       SUM(l.qty)                     AS units,
       COUNT(*)                       AS line_items,
       COUNT(DISTINCT l.user_id)      AS accounts
FROM labelled l
CROSS JOIN tot t
GROUP BY l.category_group, t.total
HAVING COUNT(DISTINCT l.user_id) >= __MIN_ACCOUNTS__
ORDER BY CASE l.category_group WHEN 'Other categories' THEN 1
                               WHEN 'Sensitive (not broken out)' THEN 2
                               WHEN 'Unknown' THEN 3 ELSE 0 END,
         SUM(l.spend) DESC;
