# Memo: Who drives spend, and how to test a win-back

**To:** Product manager | **From:** Kowshik | **Date:** 15 Oct 2026

## Bottom line
About 40% of accounts make 80% of the spend, going quiet is rarely final (about 6 in 10 lapsed accounts were active again a year later), and a win-back test would take most of a year to read at this size. Aim for a bigger lever, and agree the revenue guardrail before launching.

**Data:** order histories shared by 5,014 volunteer Amazon accounts, Jan 2018 to Oct 2022 (Open e-commerce 1.0, Berke et al., CC0). Gift cards excluded. Everything in "What we found" is **observational**.

## What we found
1. **Heavy-buying accounts carry most of the spend.** The 40.5% of accounts that shop often and spend big (30+ shopping days and $1,442+ in the last 12 months) make 80.0% of last-12-month spend (95% interval 78.8% to 81.2%). The top 10% of accounts make 36.6% (35.6% to 37.6%).
2. **Activity and spend rose, then flattened.** In Apr to Oct, 51% of accounts bought in a typical month in 2018 and 72% in 2022. Jan to Oct spend per account was 2.1x higher in 2022 than 2018 (2.0x to 2.2x), in plain dollars, not adjusted for inflation. Spend per account was $1,723 in 2021 and $1,720 in 2022.
3. **Going quiet is rarely final.** 7.1% of accounts (6.4% to 7.8%) had no purchase in the 180 days before Oct 2022. Of accounts quiet for 3 months, 21.6% (20.9% to 22.3%) buy again in a given month. About 6 in 10 accounts that were lapsed a year earlier were no longer lapsed.
4. **The heavy group is sticky.** 81% of frequent big spenders were still in that group a year later; 9% had dropped to occasional light spenders.
5. **Checked, nothing found (exploratory):** accounts that moved or lost a job in 2021 were no more likely to lapse (7.1% and 7.5% vs 7.0% with no event).

## How sure are we
- The numbers are precise for this sample (narrow intervals), but the sample is not Amazon shoppers. They are volunteers who shop a lot (the median account bought on 104 different days in 58 months).
- Nothing here shows why spending rose, or that any action would change it. We can't separate the pandemic, habit, prices and sample effects.
- No refunds are in the data, an "account" may be a whole household, and anyone who left Amazon is missing, so we can't measure churn.

## Recommended next step: test a win-back offer, but plan it first
I ran a **simulated** A/B test (a 10%-off coupon to accounts quiet for 3 months) on the real baseline. It checks the method, not the offer.
- Baseline: 21.6% of quiet accounts buy in a given month.
- To detect a **+3 point** lift (80% power, 5% significance) you need 3,094 accounts per arm (6,188 total). At about 637 quiet accounts a month, and assuming fresh ones keep arriving, that is roughly 10 months. A +1 point lift needs 26,990 per arm, which is not realistic. A +5 point lift needs 1,147 per arm, about 4 months.
- **So:** test a bigger lever or pool more traffic. Don't test small tweaks on this population.
- **Set the revenue guardrail first.** In the simulation, a coupon that truly cut revenue per account was flagged by a "not significantly lower" check only 15% of the time. Agree the biggest revenue drop per account you will accept before launch, and size the test for that too.
- **Track the health of the heavy group:** the share of frequent big spenders still in the group a year later (81% now).
