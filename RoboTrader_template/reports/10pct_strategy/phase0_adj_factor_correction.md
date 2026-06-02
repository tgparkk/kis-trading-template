# Phase 0 — P0-2b adj_factor Correction Report

Generated: 2026-05-24 15:06:26

## 1. UPDATE Summary

- Rows with adj_factor != 1.0 BEFORE update: **65662**
- Rows with adj_factor != 1.0 AFTER update:  **65662**
- Stocks corrected: **97**
- Rows touched: **65662**
- Batches: 1 x 100 stocks

## 2. Spot Check (3 cases)

### Kakao(035720) 2021-04-15 5:1 split -> OK

- close_pre (raw): 112,000
- adj_factor(pre): **5.0**  (== split_factor: OK)
- close_post (raw): 120,500
- adj_factor(post): 1.0  (== 1.0: OK)
- Note: adj_pre=5.0 (expected 5.0), adj_post=1.0 (expected 1.0)
- **Result: PASS**

### Korea Petroleum(004090) 2021-04-15 10:1 split -> OK

- close_pre (raw): 14,550
- adj_factor(pre): **10.0**  (== split_factor: OK)
- close_post (raw): 18,900
- adj_factor(post): 1.0  (== 1.0: OK)
- Note: adj_pre=10.0 (expected 10.0), adj_post=1.0 (expected 1.0)
- **Result: PASS**

### 260970 2021-02-01 10:1 split -> OK

- close_pre (raw): 379,700
- adj_factor(pre): **10.0**  (== split_factor: OK)
- close_post (raw): 32,850
- adj_factor(post): 1.0  (== 1.0: OK)
- Note: adj_pre=10.0 (expected 10.0), adj_post=1.0 (expected 1.0)
- **Result: PASS**

## 3. PIT Safety Regression

Test date: 2022-01-03
Verify: simulate adj_factor using only events with event_date > test_date,
compare to DB value. Mismatch = future event leaked into past adj_factor.

| Stock | Status | Simulated | DB value | Match | Future events |
|---|---|---|---|---|---|
| 035720 | PASS | 1 | 1.0 | yes | [] |
| 004090 | PASS | 1 | 1.0 | yes | [] |
| 260970 | PASS | 1 | 1.0 | yes | [] |

PIT regression: **OK**

## 4. P1 Forward Return Usability

- adj_factor rows corrected: yes (65662 rows)
- Spot check: 3/3 PASS
- PIT safety: OK
- **Usable for P1 forward return calculation: OK**

## 5. Algorithm

```
adj_factor(T) = product(split_factor for events where event_date > T)

- event_date > T : split not yet effective at T
                   => pre-split price needs to be divided by split_factor
                      to be comparable to post-split prices
- event_date <= T: split already effective => price already adjusted => factor 1.0
- Multiple splits: cumulative product
  e.g., 5:1 (2022-06) + 2:1 (2023-03), row at 2021-12:
      adj_factor = 5 x 2 = 10
```

> Rule 1 (No Look-Ahead): adj_factor(T) only includes events with event_date > T
> Rule 2 (Chronological): cumulative product of all future splits