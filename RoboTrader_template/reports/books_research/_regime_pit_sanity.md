# 2트랙 PIT 시장국면 — 사니티 점검 (트랙A 일봉)

> 작성: 2026-06-02 · 모듈: `core/regime/regime_classifier.py`
> 설계 출처: `_EXPERT_regime_methods.md`(트랙A) + `_EXPERT_regime_daytrading_2track.md`(트랙B/통합)
> ★No Look-Ahead: 룩어헤드 방지 테스트 5종(`tests/regime/test_regime_no_lookahead.py`) 전부 통과(14 passed).

## KOSPI 식별 / 데이터 소스
- 지수: `daily_prices` `stock_code='KOSPI'` (라이브 SSOT, 2026-05-29까지 1,324 bars). `market_index`(frozen)·`market_regime.peak_trough`(look-ahead) 미사용.
- breadth 패널: `daily_prices` 비지수 종목 큐레이션 풀(323종목) 종가 pivot. 각 종목 SMA120 대비 %above (전부 trailing).

## 파라미터 (DailyRegimeParams 기본값)
ma_window=120, slope_lb=20, breadth_window=120, breadth_hi/lo=0.55/0.45,
vol_window=20, vol_rank_window=252, vol_pct_hi=0.67, confirm_days=3.

## 연도별 국면 분포 (regime, MA120 정의 구간만)

| 연도 | bull | bear | sideways | n | 비고 |
|---|---|---|---|---|---|
| 2021 | 9% | 43% | 47% | 129 | 하반기 고점→조정 진입 |
| 2022 | 0% | **76%** | 24% | 246 | ★약세장 — BEAR 우세 (상식 부합) |
| 2023 | 13% | 22% | 65% | 245 | 박스권 회복 |
| 2024 | 11% | 34% | 55% | 244 | 횡보·간헐 조정 |
| 2025 | **62%** | 17% | 21% | 242 | ★강세장 — BULL 우세 (상식 부합) |
| 2026 | **100%** | 0% | 0% | 99 | ★대폭등 — 전구간 BULL |

vol_class: LOW 661 / HIGH 544.

## 판정
**상식 부합 ✅** — 2022 BEAR 우세(76%), 2025~26 BULL 우세(62%→100%). KOSPI 식별·파라미터 정상.
약세장(2022)을 명확히 분리하고 폭등장(2026)을 BULL로 포착. forward-only 디바운스(confirm_days=3)로 휩쏘 억제.

## 룩어헤드 방지 테스트 (필수 합격 기준) — 전부 통과
1. 절단 불변성(A): regime_at(T) == T까지 절단한 시계열 값 ✅
2. 미래 불변성(A): T 이후 변조해도 ≤T 라벨 불변(디바운스 포함) ✅
3. 장중 절단 불변성(B): bar i == bars 0..i 만으로 계산 ✅ + 미래 분봉 변조 무영향 ✅
4. trailing 윈도우: breadth/vol_pct/장중RV 전부 과거만 ✅
5. 정상(상승→bull/하락→bear) + 경계(데이터부족 안전 디폴트 sideways/LOW/range/neutral) ✅

## 다음 단계 (게이트 멀티버스 연동)
- 트랙A/B 파라미터는 dataclass 외부 주입 → `scripts/book_param_multiverse.py` 스타일 그리드 스윕 대비 완료.
- 스윕 후보: ma_window{60,120,200}·slope_lb{10,20,40}·breadth_thr·vol_pct_hi·confirm_days(A) / or_minutes·dir_thresh·breadth_hi/lo·gap_atr_thr·confirm_bars(B).
- 목적함수 = 라벨 자체가 아니라 **국면별 전략 OOS 성과 분리도**(TREND게이트 시 추세전략 Sharpe↑ / RANGE게이트 시 페이드 Sharpe↑). 정본 유니버스(top_volume:50) + 약세장 포함 OOS로 재확인(단일국면 in-sample 과적합 회피 — MEMORY 교훈).
- 트랙B 장중 vol은 현재 self-trailing 백분위(1차 대용). 라이브 시각정규화(과거 동일 분-of-day 분포)는 후속 보강 포인트.
