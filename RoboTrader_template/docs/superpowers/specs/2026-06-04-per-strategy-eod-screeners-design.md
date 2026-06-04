# 전략별 EOD 스크리너 (per-strategy candidate screeners) — 설계

- 작성일: 2026-06-04
- 상태: 설계 승인됨, 구현 계획 대기
- 관련 메모리: 가상매매 후보 선정 결함 진단(전략별 유니버스 cosmetic), `_REVIEW_per_strategy_universe.md`

## 1. 배경 / 문제

페이퍼 가동(2026-06-01~06-04) 동안 활성 5전략의 실제 장중 체결은 **1건**(06-01 332570)뿐이었다. 근본 원인은 **전략별 매수후보 선정 결함**:

1. **EOD 스냅샷이 엉뚱한 전략을 스크리닝** — `runners/screener_snapshot_collector.py:44`의 `ALL_STRATEGIES = ["lynch","sawkami","bb_reversion","sample"]`(구 템플릿)만 `screener_snapshots` DB에 저장. 활성 5전략(elder_ema_pullback, minervini_volume_dryup, book_pullback_ma20, book_pullback_ma5, daytrading_3methods_breakout) 스냅샷은 **0건**.
2. **활성 5전략은 스크리너(screener.py)가 아예 없음** — `build_adapter`가 어댑터를 만들 수 없어 후보 0.
3. **결과 체인**: 아침 `select_candidates_per_strategy`가 `WHERE strategy='<active>'`(D-1) 조회 → 0건 → `거래량 순위 fallback` → 5전략 전부 동일한 **거래량 상위 ~9 대형주** 공유 풀 → 셋업 거의 안 맞음 → 무거래.

즉 "전략별 유니버스 분리"가 실제로는 동작한 적이 없다.

## 2. 목표

각 전략이 **자기 컨셉(매수 논리)에 맞는 종목만** 후보로 받아 매매하도록, 전략별 EOD 스크리너를 구현한다.

- 비목표(범위 밖): `daily_prices` 유니버스 확대(현재 ~308종목 → 전체 KRX) = 별도 데이터 백필 사안.

## 3. 핵심 결정 (확정)

| 항목 | 결정 |
|---|---|
| 선정 기준 | **전략 진입룰 재사용** — strategy.py가 import하는 동일 rule 함수를 스크리너 match()가 그대로 사용(단일 진실원) |
| 스캔 유니버스 | **전종목(daily_prices) → 전략별 기초필터** |
| 후보 흐름 | **엄격 격리** — get_selected_stocks owner 필터, 거래량순위 폴백 제거(스크리너 0건이면 그날 미거래) |
| 스냅샷 모델 | 기존 유지 — EOD `screener_snapshots`(strategy=폴더키) 저장 → 익일 D-1 조회 |
| 구조 | 공통 `RuleScreenerBase` + 전략별 얇은 어댑터 5개 |

## 4. 아키텍처

### 4.1 데이터 / 유니버스
- 스캔 대상 = `daily_prices`에 일봉이 전략 최소봉 이상 있는 종목(현재 ~308). D-1 종가까지로 절단(no-lookahead).
- 컬럼 활용: `close/open/high/low/volume/trading_value/market_cap/returns_*`.
- 시장 구분(KOSPI/KOSDAQ): 기존 candidate_selector / stock_list 의 시장 분류 소스를 재사용(구현 시 단일 헬퍼로 확정).

### 4.2 컴포넌트
- `strategies/_rule_screener_base.py` — `RuleScreenerBase(ScreenerBase)`:
  - `scan(scan_date, params)`:
    1. `base_filter(universe_df) -> codes` (전략별 오버라이드)
    2. 각 code의 D-1 일봉 df 로드(공통, daily_prices, scan_date 이하 절단)
    3. `match(df, params) -> Optional[(score: float, reason: str)]` (전략별 오버라이드, None=탈락)
    4. score 내림차순 top-N → `List[CandidateStock]`
  - 공통 가드: 최소봉/ NaN / 룩어헤드(미래봉 제외).
- 전략별 어댑터 5개 (각 전략 폴더 `screener.py`): `strategy_name=폴더키`, `base_filter`/`match` 구현. match는 strategy.py가 쓰는 rule 함수 재사용.

### 4.3 전략별 컨셉 → 기준

| 전략 | 컨셉 | base_filter | match (진입룰 재사용) |
|---|---|---|---|
| elder_ema_pullback | 추세 중 EMA13 눌림 | KOSPI·대형(market_cap 상위·trading_value 충분) | screen1 uptrend + 저가 EMA13 부근 되돌림(triple_screen_ema_pullback) |
| minervini_volume_dryup | 상승 후 거래량 건조 | KOSPI·유동성 충분 | recent/base 거래량비 ≤ 0.70 + 상승 |
| book_pullback_ma20 | MA20 눌림목 | 중소형 눌림 풀 | 상승 종목의 MA20 부근 되돌림(daily_ma20_pull) |
| book_pullback_ma5 | MA5 단기 눌림 | 중소형 눌림 풀 | MA5 부근 되돌림(ma5_pullback) |
| daytrading_3methods_breakout | 급등주 전고 돌파 | KOSDAQ·시총<5000억 급등 | breakout_prev_high(전고 돌파) |

> 기초필터 구체 수치(시총 컷·거래대금 하한·상위 N)는 구현 시 전략별 config 파라미터로 노출. 기본값은 메모리 권고 기반(예: daytrading 시총<5000억, elder/minervini 거래대금≥50억).

### 4.4 배선 변경
- `runners/_adapter_factory.build_adapter`: 5전략 분기 추가.
- `ALL_STRATEGIES`(screener_snapshot_collector): 하드코딩 제거 → **활성 config 전략 폴더키에서 파생**.
- `core/trading_context.get_selected_stocks(owner=None)`: owner 지정 시 해당 전략 소유 SELECTED만 반환. on_tick 경로가 자기 폴더키로 호출.
- 거래량순위 폴백: 전략별 스크리너 활성 시 **비활성화**(스크리너 결과만 사용).
- D-1 휴장일 폴백: D-1에 스냅샷 없으면 **직전 거래일 스냅샷** 사용(빈 결과 방지).

## 5. 데이터 흐름

```
[EOD 15:xx] run_screener_snapshot_hook
  → ALL_STRATEGIES(=활성 config 전략)
  → 각 전략 build_adapter → scan(today) : daily_prices 스캔 + 진입룰
  → screener_snapshots 저장 (strategy=폴더키, scan_date=today)

[익일 09:00] select_candidates_per_strategy
  → 각 전략 screener_snapshots(D-1, 없으면 직전거래일) 조회 → 후보 등록(owner=폴더키)
  → on_tick: ctx.get_selected_stocks(owner=폴더키) → 자기 후보만 generate_signal
  (스크리너 0건 → 후보 0 → 그날 그 전략 미거래, 거래량폴백 없음)
```

## 6. 에러 처리 / 엣지
- 어댑터 생성 실패/스캔 예외: 해당 전략만 0건 처리(다른 전략·메인 루프 무중단). 기존 fail-open 패턴 유지.
- 일봉 부족 종목: match 진입 전 최소봉 가드로 제외.
- D-1 휴장: 직전 거래일 스냅샷 폴백. 그것도 없으면 0건(미거래).
- 룩어헤드: scan_date 이하로만 절단(미래봉 절대 미사용).

## 7. 테스트 (TDD)
- 전략별 screener(각): match 양/음성 케이스, base_filter 경계, score 랭킹, no-lookahead(미래봉 불변), 최소봉 가드.
- RuleScreenerBase: top-N 정렬, NaN/결측 가드.
- 배선: build_adapter 5전략, ALL_STRATEGIES config 파생, get_selected_stocks owner 필터, 거래량폴백 제거, D-1 휴장일 폴백.
- 회귀: 기존 4 템플릿 스크리너·기존 후보경로 테스트 무영향.

## 8. 검증 기준 (완료 정의)
- EOD 후 `screener_snapshots`에 5 활성 전략 폴더키로 스냅샷 저장(전략별 컨셉에 맞는 종목).
- 익일 아침 각 전략이 자기 후보(owner 격리)만 검토(`매수검토 N종목`에서 N이 전략별로 상이, 거래량폴백 로그 없음).
- 단위/회귀 테스트 그린.

## 9. 범위 밖 / 후속
- daily_prices 유니버스 확대(전체 KRX 일봉 백필).
- 기초필터 수치 튜닝(과적합 주의 — 멀티버스 교훈).
- `data/screener_*.json`(04-02 정지) 경로 정리 — 본 설계는 DB 스냅샷 경로만 사용하므로 JSON 경로는 별도 정리/폐기 후속.
