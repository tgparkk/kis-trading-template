# 검증된 책 전략 4종 페이퍼트레이딩 코드화 (2026-05-31)

> 사장님 지시: "지금까지 분석한 책들에 대해서 수익이 나는 전략을 코드화(페이퍼트레이딩)".
> 15권 책 조사 중 **백테스트 검증을 통과한 수익 전략**을 라이브 페이퍼 전략(BaseStrategy)으로 포팅.
> **커밋 보류** — git 커밋은 사장님 승인 필요(작업 시 취침 중). 코드·테스트·등록·문서까지 완료, 커밋만 대기.

## 선정 기준 — "수익 나는 전략" (검증 통과분만)
| 전략 | 출처 | 백테스트 | 비고 |
|---|---|---|---|
| Elder ema_pullback A | Elder 삼중창 | Sharpe 1.22, **약세장 BEAR +3.01% 방어** | 유일 CANDIDATE, 기존 라이브 존재 → 하드닝 |
| Minervini volume_dryup B | Minervini VCP | Sharpe 0.64(B)/0.03(A) | variant 의존·BULL 편향 |
| 강창권 ma20_pullback A-07 | 단기 트레이딩의 정석 | Sharpe 0.44, +16% | 책 명시 +10% 익절 |
| Book15 ma5_pullback | 트레이딩의 전설 | Sharpe 0.63 | 눌림목 최고치, BULL 청산 의존 |

> 제외: 펀더멘털/퀀트(문병로·홍용찬 Sharpe~0.1), 분봉 단타(전멸), systrader79(자산배분 별트랙). = 수익성·강건성 미달.

## 1. Elder 하드닝 (기존 `strategies/elder_ema_pullback/`)
- **미결 ④ 해결**: hold_days를 달력일`(now-entry).days` → **거래일** 기준으로 교체. `utils.korean_holidays.count_trading_days_between` 사용(주말+공휴일 제외), 진입일=0거래일차. 백테스트 bar-count와 정합(기존 100달력일≈70거래일로 조기청산되던 불일치 제거).
- **미결 ②③ 의도적 처리 명시**(docstring): ②trailing/trend_flip은 일봉 EOD 해상도 평가(swing holding_period 설계 의도) ③슬리피지·세금은 core/fund_manager 프레임워크 책임.
- 진입/청산 룰 로직 무변경. 회귀 테스트 15 passed.

## 2. 신규 라이브 페이퍼 전략 3종 (Elder 패턴 1:1 모방, 백테스트 룰 직접 import = 동등성 보장)
- `strategies/minervini_volume_dryup/` — `MinerviniVolumeDryupStrategy`. 진입=`rule_volume_dryup` 직접호출. 청산 variant B: sl−8/tp+12/max_hold 20거래일, trail·flip 없음. min_bars 40. docstring에 BULL 편향 경고.
- `strategies/book_pullback_ma20/` — `BookPullbackMa20Strategy`. 진입=`rule_daily_ma20_pullback`. 청산: sl−8/tp+10(책명시)/max_hold 50거래일/trail MA20. min_bars 35.
- `strategies/book_pullback_ma5/` — `BookPullbackMa5Strategy`. 진입=`rule_ma5_pullback`. 청산: sl−3(타이트)/tp+15/max_hold 30거래일/trail MA5. min_bars 25.
- 공통: holding_period="swing", accepts_volume_fallback=True(거래량 상위 풀), paper_trading=true, max_positions5/max_daily_trades5/종목당 300만원. 청산 우선순위 sl→tp→max_hold(거래일)→trail_ma.

## 3. 페이퍼 러너 등록 (`config/trading_config.json`)
- `paper_trading: true`(기존) 유지. `strategies` 리스트를 플레이스홀더(sample/lynch/bb_reversion) → **검증 4종으로 교체**:
  - elder_ema_pullback 0.30 / minervini_volume_dryup 0.20 / book_pullback_ma20 0.25 / book_pullback_ma5 0.25 (합 1.00, 전부 enabled).
- main.py `_load_strategies()` → `StrategyLoader.load_strategies(spec)` 다전략 라운드로빈 on_tick으로 동작. 4종 전부 로딩 검증 완료.

## 4. 검증
- 신규+회귀 테스트 **76 passed**(Elder 15·Minervini 19·ma20 18·ma5 17·다전략로드 7) + main 스모크/페이퍼 잔고 **27 passed**. 회귀 0.
- StrategyLoader 4종 로딩 OK(holding=swing, max_cap 정상).
- 동등성: 4종 모두 라이브 evaluate_entry ↔ 백테스트 rule.evaluate **trigger 일치** 확인.

## 5. 남은 실전 캘리브레이션 (페이퍼 관찰로 확인할 항목)
- 매수스톱 체결 방식(Elder Screen3 전일고가+1틱) 실전 갭 vs 페이퍼 체결 비교.
- variant B 류(Minervini·ma5) 타이트 청산이 실데이터 슬리피지에서 유지되는지.
- 거래량 상위 풀(accepts_volume_fallback)이 각 룰의 진입 유니버스와 정합한지(상한가·급등주 포함 여부).
- 다전략 동시 보유 시 자금배분(max_capital_pct)·중복신호 충돌.

## 6. 미커밋 파일 (사장님 승인 후 커밋)
- 수정: `strategies/elder_ema_pullback/strategy.py`, `config/trading_config.json`
- 신규: `strategies/{minervini_volume_dryup,book_pullback_ma20,book_pullback_ma5}/`(각 3파일) + `tests/test_strategy/test_{minervini_volume_dryup,book_pullback_ma20,book_pullback_ma5}_consistency.py`
- 커밋 범위는 위 페이퍼 코드화 파일만(타 작업 미추적 100여개 제외).
