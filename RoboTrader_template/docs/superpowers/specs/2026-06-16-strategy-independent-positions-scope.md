# 전략별 독립 포지션(완전 격리) — 범위·설계 스코핑

> **상태:** 설계/범위 조사 완료, 구현 착수 전 **사장님 결정 대기**. 코드 미변경.
> **작성:** 2026-06-16 (장마감 분석 세션)
> **결정 사항:** "완전 독립(제거)" 방향 승인됨 → 단, 코어 리팩토링이라 범위 정밀화 후 재결정.

---

## 1. 문제 정의

8개 전략이 페이퍼 모드에서 **각자 독립 1,000만원**으로 운용된다는 것이 컨셉이다. 그러나 같은 종목을 두 전략이 동시에 보유하지 못하도록 막는 **격리 레이어 2개**가 있어, 자본을 나눈 의미가 무력화된다:

- 뒤 순서 전략이 신호를 내도 종목을 뺏기거나(차선 매수=신호 열화) 현금이 놀아 **측정 성과가 오염**된다.
- 누적 리더보드(현재 rs_leader 1위 ~ minervini 꼴찌)가 전략의 진짜 엣지가 아니라 **config 나열 순서**라는 인공물에 좌우된다.
- 증거: 2026-06-16 미실현 최대 효자 010170(+9.6%)을 minervini가 보유. 로그 `010170 — rs_leader 후보 제외 (선행 전략이 이미 배정)` — rs_leader는 순서가 뒤라 뺏긴 것이지, 신호 품질 때문이 아니다.

**목표:** 각 전략이 자기 자본으로 독립적으로 동일 종목을 보유·운용할 수 있게 하여, 전략별 진짜 엣지를 오염 없이 측정한다.

---

## 2. 격리 레이어 2개 (둘 다 풀어야 진짜 독립)

| # | 위치 | 동작 | 제거 난이도 |
|---|---|---|---|
| ① 후보 dedup | `core/candidate_selector.py:855` `select_candidates_per_strategy` | 전 전략 공유 `assigned_codes` 집합 — config 순서 선착순으로 종목 배타 배정 | **쉬움** (로직 삭제) |
| ② 매수 소유권 가드 | `core/trading_context.py:331-346` `buy()` | 종목이 이미 POSITIONED/BUY_PENDING이면 다른 전략 매수 거부 | 체크 제거는 쉬우나 **하부 상태저장소가 막힘** |

①만 제거하고 ②를 두면 반쪽 수정 — 후보엔 떠도 매수단에서 막힌다.

---

## 3. 진짜 벽 — 상태저장소가 종목코드 1키

`core/trading/stock_state_manager.py:40-43`:
```python
self.trading_stocks: Dict[str, TradingStock] = {}                      # 키 = 종목코드 단독
self.stocks_by_state: Dict[StockState, Dict[str, TradingStock]] = {    # 동일
    state: {} for state in StockState
}
```

시스템 전체가 **"1종목 = 1상태 = 1소유자"** 전제. 두 전략이 010170을 들면 `trading_stocks["010170"]` 한 칸을 두고 충돌 → 나중 매수가 앞 포지션 덮어쓰기, 손익절 모니터링·매도 라우팅·DB 복원이 꼬인다.

`register_stock`(line 53-87)도 POSITIONED/BUY_PENDING 종목의 2차 등록을 명시적으로 거부한다(line 72) — ②와 같은 차단의 하부 구현.

**해결 방향:** 포지션/소유권 층의 키를 `(strategy, stock_code)` 복합키로 재설계. 시세/주문 실행 층(가격·KIS 주문은 종목 단위)은 그대로 둔다.

---

## 4. 영향 범위 (정밀 조사 결과)

### 4.1 규모
- 상태저장소 API(`change_stock_state`/`get_trading_stock`/`register_stock`/`unregister_stock`/`.trading_stocks`) 호출: **103곳 / 16개 파일**.
  - `core/orders/*`(order_db_handler, order_executor, order_monitor, order_timeout), `core/trading/*`(order_completion_handler, order_execution, stock_state_manager), `core/trading_context.py`, `core/trading_decision_engine.py`, `core/trading_stock_manager.py`, `bot/*`(initializer, liquidation_handler, position_sync, state_restorer, system_monitor, trading_analyzer).

### 4.2 이미 전략 컨텍스트를 들고 있는 곳 (유리한 점)
- `TradingStock` 모델(`core/models.py:169,204`)에 **`owner_strategy_name`·`owner_strategy` 필드 이미 존재** → 객체는 전략 정체성을 안다.
- 매도(`position_monitor.py:252-253`)는 이미 `trading_stock.owner_strategy` 우선 사용.
- 체결 매칭(`order_completion_handler.py:107-108`)은 **`order_id == current_order_id AND stock_code` 기반** → order_id가 유니크하므로 동일 종목 2전략이어도 체결은 올바른 포지션에 매칭됨(안전).
- position_monitor 보유 순회는 `stocks_by_state[POSITIONED].values()`(line 149,171) — **`.values()` 순회라 복합키여도 자연 동작**(두 포지션 모두 yield).
- **DB는 이미 지원**: `virtual_trading_records`는 PK=id·`strategy` 컬럼 보유·stock_code 유니크 제약 **없음**. `paper_strategy_equity` 리플레이도 strategy별 그룹. → **DB 스키마 변경 불필요**.

### 4.3 새 배선이 필요한 곳 (위험 지점)
- **상태저장소 API 전면**: 메서드 시그니처가 `stock_code`만 받음 → 복합키 또는 `strategy` 인자 추가 + 103개 호출부가 전략 컨텍스트를 넘기도록 수정.
- **체결 콜백 단일 전략 고정**: `order_completion_handler.set_strategy`(line 46)/`_notify_strategy_order_filled`(line 54-72)가 **단일 `self.strategy`** 에만 `on_order_filled` 통지 — 기존 알려진 한계([[diag-2026-06-11-eod-tiny-buy-sizing]] "콜백 Elder 고정"). 복합키 전환 시 체결→소유 전략 통지 라우팅 필요.
- **state_restorer(오버나잇 복원)**: DB→`trading_stocks` 복원 시 (strategy, stock_code)로 복원해야 동일종목 다전략 보유가 살아남음.
- **trading_context.buy/sell**: ② 가드 제거 + 복합키 조회로 교체, get_selected_stocks owner 격리(line 243~)와 정합.

---

## 5. 권장 단계안 (TDD, 단계별 커밋·검증)

> 전 단계 공통: 페이퍼 회귀 스위트(베이스라인 32 사전존재 실패 동일·순회귀 0) 유지. 봇 재시작 전 라이브 e2e 1회.

**Phase 0 — 안전망 (착수 전제)**
- 동일종목 2전략 동시보유 시나리오의 **현재 동작을 고정하는 특성화 테스트** 작성(현재는 차단됨을 명시). 이후 단계의 RED 기준점.

**Phase 1 — 후보 dedup 제거 (저위험, 독립 가치)**
- `select_candidates_per_strategy`의 `assigned_codes` 제거 → 각 전략 풀 독립.
- RED: "두 전략 후보에 동일 종목이 모두 남는다" 테스트.
- ②가 아직 살아있어 매수단에선 여전히 1전략만 — but 측정 오염의 절반(후보 열화)은 해소. **이 단계만으로도 부분 개선·롤백 쉬움**.

**Phase 2 — 상태저장소 복합키화 (코어, 고위험)**
- `trading_stocks`/`stocks_by_state` 키를 `(strategy, stock_code)`로. API에 strategy 인자 추가, 103 호출부 배선.
- RED: "minervini와 rs_leader가 010170을 각자 보유, 상태·손익절 독립" 테스트.
- ② 가드를 "동일 전략 내 중복만 차단"으로 완화.

**Phase 3 — 체결 콜백·복원 라우팅**
- `order_completion_handler` 다전략 통지(order_id→owner 전략), state_restorer 복합키 복원.
- RED: 체결/복원이 올바른 전략 포지션에 귀속.

**Phase 4 — equity·리포팅 정합 + 라이브 e2e**
- paper_strategy_equity 재검증(이미 strategy별), 리더보드 재산출. 봇 재시작 e2e.

---

## 6. 미해결·결정 필요 사항

1. **실전 단일풀 회귀**: 나중에 실계좌(단일 자본풀)로 가면 동일종목 다전략 보유 = 집중 리스크. 그땐 dedup이 다시 필요 → 이번 변경은 **페이퍼/평가 모드 한정**으로 플래그 가드할지, 아니면 모드 무관 독립으로 갈지 결정 필요.
2. **Phase 1만 하고 멈출지** vs 전 단계 완주: Phase 1(후보 dedup 제거)은 저위험·즉시 부분개선. Phase 2+는 코어라 운영 중단 리스크.
3. **대안(코드 무변경)**: 라이브는 그대로 두고 "각 전략이 dedup 없이 독립 운용했다면"을 재곡하는 **평가 전용 리플레이**만 산출 — 측정 오염은 해소하나 라이브 자본 활용은 여전히 비독립. (Phase 1+2의 라이브 변경을 피하고 싶을 때)

---

## 7. 다음 액션

사장님 결정 필요:
- **(A)** Phase 1만 우선(후보 dedup 제거) — 저위험, 즉시 착수 가능
- **(B)** Phase 1~4 전 단계 완주 — 진짜 완전 독립, 코어 리팩토링
- **(C)** 평가 전용 리플레이(§6.3) — 라이브 무변경, 측정만 정화

결정 시 해당 범위로 실행용 바이트사이즈 plan(`docs/superpowers/plans/`) 작성 후 TDD 착수.
