# Metric definitions

Base table: 2018-01-01 to 2022-10-31 (58 months), gift cards excluded, duplicates kept.
There is no order ID in the data, so "order" is a proxy (see below).

| Metric | Definition | Can tell us | Cannot tell us |
|---|---|---|---|
| Spend | price x quantity, in dollars | What accounts paid per item at purchase | Amazon revenue or profit; refunds (none in the file); whether tax/shipping is included |
| Units | sum of quantity | How many items were bought | Whether items were for the buyer or a gift |
| Order (proxy) | one account's purchases on one calendar day | Shopping occasions, roughly | True orders: two orders on one day merge, and one order shipped on two days splits |
| Basket | line items and spend per order (proxy) | Typical size of a shopping occasion | What was really in one checkout |
| Active user | an account with at least one base purchase in a calendar month | Share of accounts buying in a month | Why an account was quiet: left Amazon, bought elsewhere, or just skipped a month |
| Purchase frequency | order-days per account per month, averaged over the 58 months | How often accounts shop | Anything about shoppers outside this volunteer sample (heavy buyers, young, educated) |

Notes:
- A "user" is an Amazon account, which may be shared by a household.
- Active share uses a fixed denominator: the 5,014 accounts with at least one base purchase in the window.
- A month with only gift-card purchases counts as inactive.
