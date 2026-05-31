# 전략별 가상매매 재시작 영속화 — 매매기록 재구성 (2026-05-31)

> 선행: [changelog-2026-05-31-paper-readiness-per-strategy-capital.md](changelog-2026-05-31-paper-readiness-per-strategy-capital.md)의 미해결(재시작 시 전략 잔고 1천만 리셋·`_position_owner` 소실) 해결.
> 계획: `C:\Users\sttgp\.claude\plans\cozy-brewing-quill.md`

## 방식 (사장님 확정): 신규 DB 테이블 없음
전략별 현금은 매매기록의 순수 함수 → 재시작 시 기존 `virtual_trading_records`(이미 `strategy`=폴더키 저장)에서 재구성. 런타임 메모리 원장은 DB 파생값의 self-healing 캐시.
```
현금[전략] = 1천만(VIRTUAL_CAPITAL_PER_STRATEGY) − Σ매수비용 + Σ매도수익
            수수료/세금 = COMMISSION_RATE·SECURITIES_TAX_RATE 상수로 런타임과 동일 재계산
포지션[전략] = get_virtual_open_positions()의 미청산 BUY를 strategy별 그룹
집계 virtual_balance = Σ현금[전략]
```
선형식이라 action별 `Σ(qty·price)` 합산 후 배수 적용 = 런타임 per-trade 차감과 정확히 일치.

## 변경 (최소·재사용)
- `db/repositories/trading.py`: `get_strategy_trade_sums()` 신규 — `{strategy:{buy_gross, sell_gross}}` (GROUP BY strategy,action; is_test·source 필터; 예외/무결과 {}).
- `db/database_manager.py`: 위임 1개.
- `core/virtual_trading_manager.py`: `restore_strategy_ledger_from_records(initial, trade_sums, open_positions)` 신규(cash식·포지션 그룹핑·`_position_owner` 복원·집계 동기화·하위호환 가드). `execute_virtual_sell` owner 폴백 2줄(`_position_owner` miss & 전달 strategy가 폴더키면 귀속).
- `bot/state_restorer.py`: `_restore_holdings_from_db`가 복원 포지션 수집 후 재구성 호출. `_sync_virtual_balance_for_position` 첫 줄 가드(원장 활성 시 집계 차감 스킵 → 이중차감 방지).
- **변경 없음**: init-scripts/신규 테이블/EOD 훅/liquidation_handler/main.py.

## 이중차감 방지
매수비용은 cash식에만 반영, 포지션 루프는 invested/positions/owner만 채움. state_restorer의 기존 집계 차감(`_sync_virtual_balance_for_position`)은 원장 활성 시 스킵.

## 검증
- 회귀 **179 passed**(ledger·vtm·carryover·main_smoke·decision_engine·trading_context·state_restorer·state_restorer_ledger). 직원측 204 passed + 전체 2508 passed(12 fail은 사전존재·무관, stash 대조 확인).
- **재시작 패리티(관리자 독립 시뮬)**: 런타임에서 A/B 다종목 매수+청산 후, 새 VTM이 매매기록(trade_sums+open_positions)에서 재구성 → **A·B·집계 현금이 런타임 원장과 원 단위까지 일치**(A=9,709,137.50 등), `_position_owner` 복원, 재시작 후 매도가 소유전략에만 귀속(타 전략 불변).
- 하위호환: 원장 미활성(레거시/단일전략/실전) 시 재구성/폴백/가드 모두 no-op·기존 경로.

## 엣지케이스 (테스트 포함)
첫실행→1천만 유지 / swing 미청산 오버나이트→cash·invested·owner 정확 / 전략 삭제→고아자금 회수+WARNING / 부분매도→cash 정확·positions 폴백 / DB 매도 지연→eventually consistent.

## 직원 판단 2건(테스트 인프라 한정, 프로덕션 무관)
- `tests/test_database.py`에 `sys.modules['psycopg2.extensions']` 1줄 — 사전존재 mock 갭으로 db.connection import가 깨지던 것 복구(파일 59 passed).
- `tests/test_state_restorer.py` `_make_vtm`에 `_strategy_balances={}` — bare MagicMock의 auto-truthy를 실제 레거시 VTM(빈 dict)으로 정확 모델링.

## 미커밋 (사장님 승인 후)
- 소스: `db/repositories/trading.py`, `db/database_manager.py`, `core/virtual_trading_manager.py`, `bot/state_restorer.py`
- 테스트: `tests/test_database.py`, `tests/test_virtual_strategy_ledger.py`, `tests/test_state_restorer.py`, `tests/test_state_restorer_ledger.py`(신규)
- 문서: 이 changelog, SELECTED_STRATEGIES.md, paper-readiness changelog 갱신
- 앞서 미커밋(전략별 원장·일봉120) 포함 일괄/순차 커밋.
