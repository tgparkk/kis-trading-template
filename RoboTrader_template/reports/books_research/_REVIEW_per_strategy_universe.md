# 전략별 매수후보 유니버스 분리 — 설계 검토 (2026-06-02)

## 진단: 이미 절반은 구현돼 있으나 "신호 단계"에서 무력화됨
- **E6 경로 존재**: `main._load_candidates_multi_strategy` → `CandidateSelector.select_candidates_per_strategy`(screener_snapshots D-1 → screener JSON → 거래량순위 fallback, 전략간 dedup, first-strategy-wins) → `trading_manager.add_selected_stock`가 `ts.strategy_name` 태깅.
- **★load-bearing 갭**: 매수 시점 `BaseStrategy.on_tick`(base.py:541)이 `ctx.get_selected_stocks()`를 도는데, 이게 `trading_context.py:243`에서 **owner 필터 없이 전체 SELECTED 풀**을 반환. → 전략별 후보 태깅이 신호 단계에선 **무의미(cosmetic)**, 실제 격리는 `ctx.buy()`의 선점 ownership 락(first-come)만. 즉 "전략별 유니버스"가 지금은 형식상만 존재.

## `target_stocks` 필드 실태
- `BaseStrategy.get_target_stocks()`가 `config['target_stocks']`를 읽지만, 라이브 소비처는 `bot/system_monitor.py`의 `_register_strategy_target_stocks()` 하나뿐 — **`self.bot.strategy`(단수=첫 전략만)**, 1일1회 프리마켓, 공유 SELECTED 풀에 태깅. → **단일전략·정적 메커니즘**, 다중전략 유니버스 훅 아님. (bb_reversion/sawkami만 on_market_open서 동적 변경.)

## 구현 옵션 3
| 옵션 | 내용 | 개발량 | 비고 |
|---|---|---|---|
| **A 정적 target_stocks** | 전략별 config에 종목 채우고 system_monitor가 전 전략 루프+on_tick owner필터 | 최저 | 정적·stale·수동유지, 급등주 무갱신 |
| **B CandidateSelector 전략분기** | `_fetch_candidates_for_strategy`에 전략→유니버스빌더 맵(유지윤=surge-smallcap, Elder=KOSPI추세) 추가, `_surge_smallcap_codes` 재사용 | 중 | 동적, E6 dedup 재사용 — **즉시 가능 interim** |
| **C 전략별 스크리너 플러그인** | `ScreenerBase` 어댑터(surge/pullback/large-trend) 작성 → `screener_snapshot_collector` EOD 적재 → 라이브가 D-1 스냅샷 read | 최고 | **아키텍처 의도된 정본**, 구조상 no-lookahead |

**추천**: 유니버스 소스는 **C(정본)**, 단 **공통 필수 선결 = `get_selected_stocks(owner=)` 필터 추가**(E6/C 분리를 실효화). EOD 스크리너 잡 즉시 스케줄 불가 시 **B를 interim**으로.

## 5전략 권장 유니버스
| 전략 | 권장 유니버스 | volume_fallback |
|---|---|---|
| elder_ema_pullback | KOSPI 중·대형 추세(거래대금순) | True |
| minervini_volume_dryup | KOSPI 대형 dryup + 52주 신고가 근접 | True |
| book_pullback_ma20 | 시장 전반 MA20 눌림 후보 | True |
| book_pullback_ma5 | 더 타이트한 MA5 눌림(ma20과 동족 풀) | True |
| daytrading_3methods(유지윤) | **KOSDAQ 급등·소형(surge:N, 시총<5000억)** | **False**(전용풀 비면 매매 대신 스킵) |

## 주의 (no-lookahead·라이브)
1. **D-1 EOD 스냅샷** 사용(라이브 경로가 이미 전일 조회) — 당일 부분봉으로 surge 재계산 금지(day-1 미확정봉 버그 동일).
2. **market_cap 소스 정책** — `daily_prices.market_cap` partial/stale → 라이브 소스(KIS API vs DB) + "미상→통과 or 제외" 정책 사전확정.
3. **스냅샷 키 = 폴더키 일관** — `screener_snapshots.strategy`와 provider가 폴더키로 통일(SELL 레코드서 한번 터진 SSOT 위험).
4. **first-strategy-wins dedup → config.strategies 순서 영향** — 유지윤이 자기 급등주를 항상 선점하려면 순서/예약 명시.
5. **`get_selected_stocks` owner필터는 동작 변경** → `len(strategies)>1`일 때만 적용(단일전략 하위호환, test_phase_e6 보존).

## 추천 로드맵
1. **선결**: `get_selected_stocks(owner=)` owner필터 + on_tick 매수루프 필터(다중전략 게이트). 이게 없으면 어떤 유니버스 분리도 형식상만.
2. **interim(B)**: CandidateSelector 전략분기 + 유지윤 KOSDAQ surge 풀(`_surge_smallcap_codes` 라이브 포팅) + accepts_volume_fallback=False.
3. **정본(C)**: 전략별 ScreenerBase 어댑터 → EOD screener_snapshots 적재 → 라이브 D-1 read. market_cap 소스 확정.
