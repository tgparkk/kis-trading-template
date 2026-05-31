# 가상매매 가동 준비 + 전략별 자금 격리 (2026-05-31)

> 사장님 지시: 검증 책전략 4종을 내일 바로 가상매매. 추가 요청: **전략별 개별 1천만원**(총 4천만) 운용.
> 선행: [changelog-2026-05-31-book-strategies-paper-codification.md](changelog-2026-05-31-book-strategies-paper-codification.md)

## 1. 일봉 수집 기간 상향 (Elder 가동 전제)
- 봇 일봉 수집이 60달력일(≈43영업일)이라 Elder(70봉 요구)가 신호 0건이던 문제 해결.
- `config/constants.py`: `OHLCV_LOOKBACK_DAYS` 60→**120**, `CANDIDATE_DAILY_FETCH_DAYS` 60→**120** (≈85영업일 ≥ 70). `main.py:766`이 OHLCV_LOOKBACK_DAYS로 일봉을 조회해 generate_signal에 전달.
- VIRTUAL_MODE는 별도 env가 아니라 `trading_config.json paper_trading:true`로 결정(`trading_decision_engine.py:49`) — 이미 ON.

## 2. 전략별 자금 격리 (VirtualTradingManager 원장 개조)
**문제**: 기존 가상매매는 단일 1천만 공유 계좌 + 전략 무관(`max_capital_pct` 미배선, VirtualTradingManager가 strategy를 모름). "전략별 1천만"이 config만으로 불가.

**구현** (TDD, 하위호환 유지):
- `core/virtual_trading_manager.py`: 전략별 원장 추가 — `_strategy_balances/_strategy_invested/_strategy_positions/_strategy_initial/_position_owner`. 신규 `allocate_strategy_capital(key, amount)`, `get_strategy_balance/positions`, `_has_strategy_ledger`, `_sync_aggregate_from_strategies`. `execute_virtual_buy`(전략 잔고 부족 거부·차감·소유권 기록), `execute_virtual_sell`(`_position_owner`로 소유 전략 복구), `get_max_quantity(price, strategy_name)`(전략 잔여 한도 기준).
- **strategy 폴더키 관통**: `trading_context.buy()`(`strategy_name=self._strategy_key`) → `trading_analyzer.analyze_buy_decision` → `trading_decision_engine.execute_virtual_buy`(`ledger_key=strategy_name`) → `get_max_quantity(strategy_name=ledger_key)` + `execute_virtual_buy(strategy=ledger_key)`. 할당·전달·원장이 **모두 폴더키**로 일치. DB 표기명(`owner_strategy_name`)은 클래스명 분리 유지.
- `config/constants.py`: `VIRTUAL_CAPITAL_PER_STRATEGY = 10_000_000`.
- `main.py`: `_load_strategies()` 직후 `_allocate_strategy_capital()` — 가상모드+vtm 존재 시 `self.strategies` 각 폴더키에 1천만 할당(집계 4천만). fund_manager total_funds도 집계로 동기화.
- `config/trading_config.json`: max_capital_pct 균등 0.25(표기 일관, 원장은 flat 1천만).

**하위호환**: 원장 미할당(레거시/단일전략/실전)이면 모든 경로가 기존 단일 `virtual_balance`로 분기.

## 3. 검증
- 회귀+신규 **127 passed**(ledger10 + vtm + carryover + main_smoke + trading_context + decision_engine). 회귀 0.
- **독립 4전략 시나리오**(관리자 직접): 4전략×1천만=4천만 집계 ✓ / elder 50주 매수→elder만 차감·minervini 1천만 불변 ✓ / elder 매도(+5%)→elder만 복구 ✓ / 종목당 한도 100주(=100만) ✓.
- end-to-end 폴더키 관통 라인 직접 확인(context:352→analyzer:140→engine:449/456/465).

## 4. 내일 가동 체크리스트
1. `paper_trading:true`(가상매매) ✓  2. 일봉 120일 ✓  3. 4전략×1천만 자동 할당 ✓
2. 실행: `run_robotrader.bat`. 신호는 선별적(급등 후 눌림)이라 매일 쏟아지지 않음 = 정상.

## 5. 미해결 / 후속
- ~~전략별 carryover 영속화 미구현~~ → **해결됨**(2026-05-31, 매매기록 재구성 방식). 상세: [changelog-2026-05-31-restart-reconstruction.md](changelog-2026-05-31-restart-reconstruction.md).
- 테스트 격리 잔존 이슈(loader 통합 테스트가 main_smoke와 결합 시 깨지는 건): CWD 상대경로 config 로딩 기인, 별도 정리 권장(런타임 무관).

## 6. 미커밋 (사장님 승인 후)
- 수정: `config/constants.py`, `config/trading_config.json`, `core/virtual_trading_manager.py`, `core/trading_decision_engine.py`, `core/trading_context.py`, `bot/trading_analyzer.py`, `main.py`, `reports/books_research/SELECTED_STRATEGIES.md`
- 신규: `tests/test_virtual_strategy_ledger.py`, 이 changelog, (전 커밋 분: SELECTED_STRATEGIES.md는 신규)
