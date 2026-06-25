# 2026-06-25 ②개선 1단계(유니버스/국면) — 파일럿 차단 findings

## 결론(확정): 정본 백테스트 harness가 의도 유니버스를 표현 못 함 = 측정 정합 갭

ma5·ma20 유니버스/국면 재측정을 시도하던 중, **정본 returns/멀티버스 harness가 라이브 스크리너의 유니버스를 재현할 수 없음**을 확인. 이것이 1단계의 진짜 선결 과제다.

### 근거
- `scripts/multiverse4_returns_export.py` 유니버스 = `_load_top_volume_daily(start, end, top_n)` (line 59 import, 277-284 사용). **거래량 상위 N(top_n=50, rs_leader만 300)** 로 구성 → 사실상 대형주.
- **시총(market_cap) 필터·KOSPI/KOSDAQ 라벨·거래대금 컷 없음.** `scripts/exit_multiverse/`·`backtest/` 어디에도 시총/거래대금 기반(=라이브 스크리너 `base_filter`) 유니버스 로더 부재(grep 확정).
- 반면 **라이브 스크리너**는 `_rule_screener_base.base_filter`(max_market_cap·min_trading_value)를 quant `get_universe_snapshot`(market_cap·trading_value 포함)에 적용 = **시총/거래대금 필터된 유니버스**. ma5·ma20 의도 유니버스 = 중소형 시총≤3조·KOSPI+KOSDAQ.

### 함의
1. **F1(ma5 sl)의 −52~−65%는 대형주 top50에서 측정** = 의도 유니버스(중소형) 아님 → 그 절대치는 라이브 거동을 대표하지 않음(sl 보류 결정 자체는 유효: sl 간 차이는 유의하지 않았으므로).
2. **백테스트↔라이브 "유니버스 정합"이 깨져 있다.** 우리가 2026-06-25에 고친 진입/청산 정합(A~E)과 동일한 결의 갭 — 다만 이번엔 *유니버스* 레이어. 의도 유니버스로 측정하기 전엔 유니버스/국면 스윕이 무의미(잘못된 모집단 측정).

## 선결 과제(②개선 1단계의 실제 첫 작업)
**스크리너-정합 백테스트 유니버스 로더** 신설/연결: quant `get_universe_snapshot`(또는 daily_prices의 market_cap/trading_value)에 전략 어댑터 `base_filter`를 적용해, 백테스트 유니버스 = 라이브 EOD 스크리너 유니버스가 되도록. 그 위에서만 유니버스(시총컷·top-N)·국면(none/exclude_bear) 스윕이 라이브를 대표한다.

## 옵션
- **α** 스크리너-정합 유니버스 로더 구축(TDD) → 그 위에서 8전략 유니버스/국면 멀티버스. (정공법·바운드된 dev 작업)
- **β** top-volume를 근사 proxy로 두고 top_n만 스윕(시총 정합 포기, 제한적).
- **γ** 여기서 ②개선 보류 — A~E 정합 완료분만 라이브 재시작·관찰 후 재개.

## 잔여 불확실성
- 정본 문서(PAPER_STRATEGIES)의 전략별 Sharpe가 어느 harness/유니버스로 산출됐는지 전수 미확인(harness 다수). 일부는 top-volume, 일부는 다른 경로 가능 → 별도 점검 필요.
- regime_gate(exclude_bear)를 백테스트가 모델링하는지 미확정(로더 갭에 막혀 측정 미도달).
