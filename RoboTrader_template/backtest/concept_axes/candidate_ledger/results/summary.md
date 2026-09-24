# candidate_ledger — summary

> 🔴 관측 원장 · 판정 근거 아님 · 룰 변경 근거 인용 금지(PREREG §0·§8-7). 순위 구간별 수익 비교표 없음(§9).

- git sha `e11fc7539eef5e116db62401436575fd12f22ed7` · 창 2024-03-13~2026-09-23 · 스캔 거래일 617 · DB 지문 sha256 `59c14921cde274f0…`
- 실행 1168s (로드 32s · 스캔 903s · 청산 228s) · 시작 2026-09-24T15:37:33 · 끝 2026-09-24T15:57:01

## 전략별

| 전략 | 행 | 시가 있음(로트) | band_ok=True | band_ok 비율 | no_open | no_next_day | band_out | n_passed 최소/중앙/최대 | n_impossible 합 | n_errors 합 |
|---|---|---|---|---|---|---|---|---|---|---|
| book_pullback_ma20 | 24,937 | 24,913 (0.999) | 18,348 | 0.736 | 0 | 24 | 6565 | 2/36/126 | 1213 | 0 |
| minervini_volume_dryup | 9,367 | 9,355 (0.999) | 8,571 | 0.916 | 0 | 12 | 784 | 0/14/60 | 848 | 0 |
| daytrading_3methods_breakout | 18,236 | 18,200 (0.998) | 15,122 | 0.831 | 0 | 36 | 3078 | 1/26/117 | 595 | 0 |

## exit_reason 분포(시가 있는 로트 전부 · band_out 가상 로트 포함 · 라이브 근사는 band_ok=True 로 거를 것)

- book_pullback_ma20: sl 13,455 · tp 9,543 · trail_ma 1,457 · open 407 · max_hold 51
- minervini_volume_dryup: sl 5,299 · tp 3,595 · max_hold 395 · open 66
- daytrading_3methods_breakout: sl 6,983 · tp 6,881 · max_hold 4,207 · open 129

## 실행시간 · 전체 추정

- 스캔 1일 평균(전략 합) 1.46s · 청산 시뮬 1일 평균 0.37s · 고정 로드 31s
  - book_pullback_ma20: 스캔 0.61s/일 · 청산 0.21s/일 · 행 24,937
  - minervini_volume_dryup: 스캔 0.45s/일 · 청산 0.06s/일 · 행 9,367
  - daytrading_3methods_breakout: 스캔 0.40s/일 · 청산 0.10s/일 · 행 18,236
- 전체 617일 예상 ≈ 0.32시간 · 4시간 초과: 아니오

## §10 검증 (V1~V5 · 값만 · 판정은 verifier)

### V1 스냅샷 일치율 (재스캔 rank≤10 ∩ 라이브 rank_in_snapshot≤10 ÷ 라이브 rank≤10 행수)

| 전략 | params_hash | 구간 | 일수 | 평균 | 최소 | 중앙 | 최대 | 대표 |
|---|---|---|---|---|---|---|---|---|
| book_pullback_ma20 | 9f2ad26d81357cee7c8044c55f910bba04fb7ead | 2026-06-05~2026-09-22 | 73 | 0.982 | 0.900 | 1.000 | 1.000 | 현행 ✓ |
| book_pullback_ma20 | 스냅샷 없는 날 3일 | 2026-06-18, 2026-07-07, 2026-07-08 | | | | | | |
| minervini_volume_dryup | 57d3ec29583ed81aef0dcdb6c3f6f39baacf5e3d | 2026-06-05~2026-08-14 | 47 | 0.011 | 0.000 | 0.000 | 0.100 |  |
| minervini_volume_dryup | 5b3a724ac392d74083b52aa2e6b11fa5bebcad98 | 2026-08-18~2026-08-24 | 5 | 0.040 | 0.000 | 0.000 | 0.100 |  |
| minervini_volume_dryup | ec452661a982b57e7d319b3552af0796e3b4947c | 2026-08-25~2026-09-22 | 21 | 0.963 | 0.500 | 1.000 | 1.000 | 현행 ✓ |
| minervini_volume_dryup | 스냅샷 없는 날 3일 | 2026-06-18, 2026-07-07, 2026-07-08 | | | | | | |
| daytrading_3methods_breakout | 545d9f26c0493cd9b5619d435af4ccbd2b8dd0a7 | 2026-06-05~2026-06-22 | 11 | 0.918 | 0.500 | 1.000 | 1.000 |  |
| daytrading_3methods_breakout | 0d80c2c3663a3a8e9e407fecf5426b24cffddc44 | 2026-06-23~2026-09-22 | 62 | 0.972 | 0.500 | 1.000 | 1.000 | 현행 ✓ |
| daytrading_3methods_breakout | 스냅샷 없는 날 3일 | 2026-06-18, 2026-07-07, 2026-07-08 | | | | | | |

### V2 행수 = Σ n_passed · 날짜별 n_passed = scan_diag.n_matched

- book_pullback_ma20: 행 24,937 · Σn_passed 24,937 · Σn_matched 24,937 · 불일치 날짜 0
- minervini_volume_dryup: 행 9,367 · Σn_passed 9,367 · Σn_matched 9,367 · 불일치 날짜 0
- daytrading_3methods_breakout: 행 18,236 · Σn_passed 18,236 · Σn_matched 18,236 · 불일치 날짜 0

### V3 사이징·밴드 항등

- 시가 있는 행 52,468 · |qty×entry−notional|>1원 0 · band_ok 재계산 불일치 0

### V4 청산 행 날짜·보유일

- 청산 행 51,866 · exit_date<entry_date 0 · hold_days>max_hold(비유예) 0 · max_hold_deferred 행 1(그중 초과 1)

### V5 층화 5행(시드 20260924) — 손계산 대조는 verifier

| 층 | strategy | scan_date | code | ref_close | band_lo | band_hi | entry_date | entry_price | band_ok | qty | exit_date | exit_price | exit_reason | pnl_won |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| book_pullback_ma20 | book_pullback_ma20 | 2024-03-29 | 109610 | 4445 | 4089.4 | 4489.45 | 2024-04-01 | 4535 | False | 220 | 2024-04-12 | 4550 | trail_ma | 3300 |
| minervini_volume_dryup | minervini_volume_dryup | 2026-06-15 | 018880 | 5680 |  | 5850.4 | 2026-06-16 | 5710 | True | 175 | 2026-06-16 | 5253.2 | sl | -79940 |
| daytrading_3methods_breakout | daytrading_3methods_breakout | 2024-12-26 | 015360 | 11440 |  | 11783.2 | 2024-12-27 | 10760 | True | 92 | 2024-12-27 | 9684 | sl | -98992 |
| trail_ma | book_pullback_ma20 | 2026-02-10 | 211050 | 14220 | 13082.4 | 14362.2 | 2026-02-11 | 14250 | True | 70 | 2026-02-26 | 14670 | trail_ma | 29400 |
| band_out | daytrading_3methods_breakout | 2026-05-08 | 320000 | 9970 |  | 10269.1 | 2026-05-11 | 11400 | False | 87 | 2026-05-11 | 12540 | tp | 99180 |

