# 실매매 가드 결선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 주문에 소유 전략을 실어 보내 죽어 있던 실매매 가드 3개(자금 상한·보유 K 한도·엔트리 누수)를 살리되, 둘 다 **섀도우 모드**로 시작해 페이퍼 매매 동작을 0줄로 유지한다.

**Architecture:** 중심 변경은 **하나** — `Order` 에 `owner_strategy` 필드. 나머지는 그 결과다. `fund_manager` 는 전략을 «문자열 꼬리표»로만 받고 해석하지 않는다.

**Tech Stack:** Python 3.8+ · `psycopg2` · PostgreSQL 16(`kis_template`, port **5433**) · pytest

**설계문서:** `docs/superpowers/specs/2026-08-13-live-trading-guards-design.md` (커밋 `116e16f`)

## Global Constraints

- **페이퍼 매매 동작 0줄.** 두 가드 모두 기본이 섀도우(`strategy_cap_enforce=False` · `position_k_enforce=False`)이고, `can_add_position` 은 애초에 페이퍼 매수 경로에 결선돼 있지 않다(2026-07-29 사장님 결정 — **결선하지 말 것**).
- **owner 를 «조회»로 얻지 말 것.** `order_monitor.py:361-363` 이 명시적으로 거부한다 — *"owner 없는 슬롯 조회를 새로 추가하면 다중소유에서 임의 소유자를 집게 된다"*. **호출자가 실어 보낸다.**
- **파싱·계산 실패는 `None` 또는 WARNING. 조용히 `0`으로 뭉개지 말 것.** 특히 `_invested_by_strategy` 가 음수로 갈 상황은 **WARNING 필수** — 뭉개면 「감소가 두 번 돌았다」는 사실이 사라진다.
- **`fund_manager` 의 모든 상태 변경은 `self._lock`(RLock) 안에서.** 새로 추가하는 `_reservation_owner` 도 같은 락 아래 금액과 **원자적으로 함께** 움직여야 한다.
- **`order_reservations` 자료구조를 바꾸지 말 것** — `has_reservation:388` 이 `.get(order_id, 0) > 0` 으로 숫자를 가정하고, 읽는 곳이 14군데다.
- **로거**: `utils.logger.setup_logger(__name__)`. **시간**: `utils.korean_time.now_kst()`.
- 전체 스위트는 **repo 루트 + VS 번들 Python** 에서만 완주. 회귀 판정은 **실패 «집합» 차분**.
- 🔴 **라이브 트리에서 테스트를 돌리지 말 것.** 워크트리에서 작업한다(`superpowers:using-git-worktrees`).

## File Structure

| 파일 | 변경 | 책임 |
|---|---|---|
| `core/models.py` | +1 필드 | `Order.owner_strategy` |
| `core/orders/order_executor.py` | 시그니처 2 + 생성 4곳 | 주문에 owner 를 싣는다 |
| `core/trading/order_execution.py` | 2줄 | 호출자가 owner 를 넘긴다 |
| `core/orders/order_monitor.py` | 2줄 | owner 를 소비(등록·회수) |
| `core/orders/order_timeout.py` | 1줄 | owner 를 소비(등록) |
| `core/fund_manager.py` | 핵심 | 예약 꼬리표 · 감소 3경로 · 섀도우 2종 · K 한도 |
| `main.py` | 1줄 | `strategy_max_pct_provider` 주입 |
| `bot/initializer.py` | +1 호출 | `k_by_strategy` 주입 |
| `tools/daily_trading_summary.py` | +2줄 | EOD 섀도우 리포트 |
| `tests/...` | 신규 4파일 | 테스트 14개 |

---

## Task 1: 선행 측정 — 런타임 엔트리가 DB 기준선과 «일치»하는가

> **🔴 2026-08-13 정정 — 이 Task 의 질문이 바뀌었다.**
> 원안은 *"런타임 엔트리에 owner=None 이 있는가"* 였고 Step 2 Expected 는
> *"`owner 없음` 이 0이 아니면 즉시 기록할 것"* 이었다. **그 기대치는 페이퍼
> 모드에서 발동 불가능하다.** `add_position` 생산자를 전수조사한 결과:
>
> | 호출자 | owner 전달 | 경로 |
> |---|---|---|
> | `bot/state_restorer.py:247` | ✅ | 복원 |
> | `bot/trading_analyzer.py:197` | ✅ (슬롯 객체 `trading_stock.owner_strategy_name`) | **페이퍼 매수** |
> | `core/orders/order_monitor.py:370` | 🔴 없음 | 실주문 체결 |
> | `core/orders/order_timeout.py:294` | 🔴 없음 | 실주문 타임아웃 |
>
> owner 를 빠뜨리는 두 경로는 **둘 다 실주문 경로**다. 그리고
> `core/orders/order_monitor.py:364-365` 가 **스스로** 적어놨다 —
> *"⚠️ 실전 전환 blocker: 이 경로는 페이퍼 모드에선 pending_orders 자체가 비어
> **휴면이라 무해**하나, 실전 모드에선 …"*
>
> ⇒ **페이퍼 모드에서 런타임 owner=None 은 구조적으로 0 일 수밖에 없다.**
> ⇒ ***0 을 관측해도 blocker 가 반증되지 않는다.*** 🔑 *데이터 부족이 「정상
> 라벨」로 나오는 경로는 경보로 절대 안 잡힌다* 의 또 다른 사례다.
>
> **재정의(사장님 승인 완료): 질문은 「owner=None 찾기」가 아니라
> 「런타임 엔트리가 DB 기준선과 일치하는가」다.** 불일치가 나오면 그게 곧
> 다른 종류의 누수다. blocker 자체는 여기서 반증되지 않으므로 Task 2~ 로 간다.

**Files:**
- Create: `scripts/probe_position_entries.py`
- Modify: `bot/state_restorer.py` (진단 로그 1블록)

**Interfaces:**
- Consumes: (없음)
- Produces: 콘솔 리포트 — 총 엔트리 / 고유 종목 / 전략별 분포 / 같은 종목 다중소유 / `owner=None` 목록 / **두 판정 방법의 대칭 차분**

설계 §10-1 이 남긴 항목이다. §6 의 DB 측정(미청산 48 / 고유 47 / 겹침 1)은
`virtual_trading_records` 기준이고 **런타임 `fund_manager._position_entries` 기준이 아니다.**
🔑 ***두 값이 다르면 그 차이가 곧 누수다.***

**DB 기준선 (2026-08-13 종가 후 측정, 두 독립 방법이 대칭 차분 양방향 0 으로 일치):**

- 엔트리 **48** / 고유 종목 **47** / **owner 없음 0**
- `elder_ema_pullback` 16 · `daytrading_3methods_breakout` 8 · `book_pullback_ma20` 6 ·
  `minervini_volume_dryup` 6 · `book_envelope_200d` 5 · `rs_leader` 4 · `book_pullback_ma5` 3
- 겹침 1건: **003280** = `book_pullback_ma5` + `minervini_volume_dryup` (2.1%)
- `SELL` 595행 **전부** `buy_record_id` 를 갖는다(NULL 0건) → **정확 링크가 가능하다.**

- [x] **Step 1: 프로브 스크립트 작성**

판정은 **`buy_record_id` 정확 링크**로 한다(원안의 `(stock_code, strategy, timestamp>)`
휴리스틱은 분할매수 BUY 2 : SELL 1 에서 갈릴 수 있다 — **2차 교차검증용으로 남기고
두 결과의 대칭 차분을 양방향으로 출력**한다).
🔑 ***단독 단언은 판별력이 없다 — 두 방법이 갈리면 그 자체가 발견이다.***
기준선 값은 스크립트 docstring 에 「2026-08-13 측정치」로 박고, 다르면 `[!]` 로 출력한다.

핵심은 두 판정 SQL 이다 (전문은 실제 파일 참조):

```python
# 1차(정확): buy_record_id 링크. action='SELL' AND buy_record_id IS NOT NULL 에
# UNIQUE 인덱스가 걸려 있어 BUY 1 : SELL 1 대응이 보장된다.
SQL_EXACT = """
SELECT b.id, b.stock_code, COALESCE(b.strategy, '(null)')
FROM virtual_trading_records b
WHERE b.action = 'BUY'
  AND NOT EXISTS (
    SELECT 1 FROM virtual_trading_records s
    WHERE s.action = 'SELL' AND s.buy_record_id = b.id)
ORDER BY b.id
"""

# 2차(교차검증): 원안의 휴리스틱. 같은 종목·전략에 «나중» SELL 이 하나라도 있으면
# 닫힌 것으로 본다 → 분할매수(BUY 2 : SELL 1)에서 1차와 갈릴 수 있다.
SQL_HEURISTIC = """
SELECT b.id, b.stock_code, COALESCE(b.strategy, '(null)')
FROM virtual_trading_records b
WHERE b.action = 'BUY'
  AND NOT EXISTS (
    SELECT 1 FROM virtual_trading_records s
    WHERE s.action = 'SELL' AND s.stock_code = b.stock_code
      AND s.strategy IS NOT DISTINCT FROM b.strategy
      AND s.timestamp > b.timestamp)
ORDER BY b.id
"""

# 1차 방법의 «전제» 점검 — 0 이 아니면 정확 링크가 깨진다는 뜻이다.
SQL_ORPHAN_SELL = """
SELECT COUNT(*) FROM virtual_trading_records
WHERE action = 'SELL' AND buy_record_id IS NULL
"""
```

두 결과의 대칭 차분은 `b.id` 집합으로 **양방향** 계산한다(`only_exact` / `only_heur`).
읽기 전용 — `INSERT/UPDATE/DELETE` 를 절대 실행하지 않는다.

- [x] **Step 2: 실행**

```bash
cd D:/tmp/wt-live-guards/RoboTrader_template     # 🔴 라이브 트리에서 돌리지 말 것
python scripts/probe_position_entries.py
```

~~Expected: **`owner 없음` 이 0이 아니면 즉시 기록할 것.**~~ ← **폐기**(위 정정 참조:
페이퍼에서 발동 불가능한 기준이다).

**Expected(정정):** 출력이 **DB 기준선과 일치**해야 한다 — 엔트리 48 / 고유 47 /
owner 없음 0 / 전략별 분포 7종 / 겹침 003280 1건 / 대칭 차분 **양방향 0**.
🔴 **어긋나면 그 차이를 기록할 것.** `owner 없음` 이 0 인 것은 **정상이며 blocker 의
반증이 아니다**(기준선 이후 매매가 있었다면 총량이 변하는 것도 정상 — 같은 날짜인데
다를 때만 조사).

**실측(2026-08-13 21:28 실행):** 기준선 및 전략별 분포 **완전 일치**.
`SELL 595행 / buy_record_id IS NULL 0행` → 정확 링크 성립. 대칭 차분 **양방향 0**
(즉 이 데이터에는 분할매수로 두 방법이 갈리는 사례가 없었다).

- [x] **Step 3: 봇 측 진단 로그 심기**

원안은 `:474` 근처라고만 적었다. **실제 위치를 확인한 결과** `"N/N 복원 완료"` 로그는
`_restore_holdings_from_db:731`(가상) 과 `_restore_holdings_from_real_account:936`(실전)
**두 곳**이고, 둘 다 직후에 `_log_fund_sync_summary()` 를 호출한다. `:474` 는 바로 그
공통 함수 안의 요약 로그다. ⇒ **`_log_fund_sync_summary` 의 `logger.info` 직후 한 블록**
이면 가상·실전 **두 경로를 한 번에** 덮고, 함수 진입부(`:461`)의 `if not self.fund_manager:`
조기 반환이 **None 가드를 이미 해준다.**

```python
        # ── 진단(2026-08-13) — 런타임 엔트리 ↔ DB 기준선 대조 ─────────────────
        # 목적은 «owner=None 탐지»가 «아니다» (위 정정 참조).
        # 기준선(2026-08-13 종가 후): 엔트리 48 / 고유 47종목 / owner 없음 0.
        # 진단 전용 — 프로덕션 동작 0줄이고, 어떤 예외도 복원 흐름으로
        # 전파시키지 않는다(실패 시 WARNING 만).
        try:
            from collections import Counter as _Counter
            _registry = getattr(self.fund_manager, '_position_entries', None)
            if isinstance(_registry, (set, frozenset)):
                with self.fund_manager._lock:
                    _entries = list(_registry)
                _dist = _Counter(owner or "(none)" for _, owner in _entries)
                logger.info(
                    f"[진단] 런타임 포지션 엔트리 {len(_entries)}건 / "
                    f"고유 {len({c for c, _ in _entries})}종목 / "
                    f"소유자별 {dict(_dist)} "
                    f"(DB 기준선 2026-08-13: 48건/47종목/owner없음 0)"
                )
        except Exception as e:
            logger.warning(f"[진단] 런타임 포지션 엔트리 분포 출력 실패: {e}")
```

원안 스니펫에서 바뀐 점 3가지:
1. **`_lock` 안에서 스냅샷** — `_position_entries` 는 다른 스레드가 변경하는 set 이라
   맨몸 순회는 `RuntimeError: Set changed size during iteration` 위험이 있다.
   `_lock` 은 RLock 이라 재진입 안전하다.
2. **`isinstance` 타입 가드** — 원안은 `len(self.fund_manager.current_position_codes)` 를
   따로 읽었으나, 같은 스냅샷에서 고유 종목을 세면 두 값의 «기준 시각»이 어긋나지 않는다.
   가드는 테스트의 `MagicMock` fund_manager 에서 헛 WARNING 이 나는 것도 막는다.
3. **`try/except` 로 격리** — 진단이 복원 흐름을 깨면 안 된다.

- [ ] **Step 4: 커밋** *(사장님 승인 후 코디네이터가 수행)*

```bash
git add RoboTrader_template/scripts/probe_position_entries.py \
        RoboTrader_template/bot/state_restorer.py \
        RoboTrader_template/docs/superpowers/plans/2026-08-13-live-trading-guards.md
git commit -m "chore(diag): 런타임 포지션 엔트리 소유자 분포 프로브 — DB 미청산과 대조용"
```

> 원안의 `git add scripts/probe_position_entries.py` 는 **경로가 틀렸다** — git 루트는
> 워크트리 루트이고 두 파일 모두 `RoboTrader_template/` 아래다.

---

## Task 2: `Order.owner_strategy` — 주문에 소유 전략을 싣는다

**Files:**
- Modify: `core/models.py:107` (Order 필드 추가)
- Modify: `core/orders/order_executor.py` — `place_buy_order:46` · `place_sell_order:237` 시그니처, `Order(` 4곳(`:118`·`:168`·`:287`·`:356`), 재주문 2곳(`:513`·`:519`)
- Modify: `core/trading/order_execution.py:229`·`:366`
- Test: `tests/test_order_owner_strategy.py`

**Interfaces:**
- Consumes: (없음)
- Produces:
  - `Order.owner_strategy: str = ""`
  - `place_buy_order(stock_code, quantity, price, timeout_seconds=None, target_profit_rate=None, stop_loss_rate=None, owner_strategy: str = "")`
  - `place_sell_order(..., owner_strategy: str = "")`

- [ ] **Step 1: 실패하는 테스트**

```python
# tests/test_order_owner_strategy.py
from datetime import datetime
from core.models import Order, OrderType, OrderStatus


def test_order_carries_owner_strategy():
    """주문이 소유 전략을 들고 다녀야 한다. 이게 없어서 가드 3개가 죽었다."""
    o = Order(order_id="X1", stock_code="005930", order_type=OrderType.BUY,
              price=70000, quantity=10, timestamp=datetime.now(),
              owner_strategy="elder_ema_pullback")
    assert o.owner_strategy == "elder_ema_pullback"


def test_order_owner_defaults_to_empty_not_none():
    """기본값은 빈 문자열이다. None 이면 소비처가 전부 None 체크를 따로 해야 한다."""
    o = Order(order_id="X2", stock_code="005930", order_type=OrderType.BUY,
              price=70000, quantity=10, timestamp=datetime.now())
    assert o.owner_strategy == ""
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_order_owner_strategy.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'owner_strategy'`

- [ ] **Step 3: 필드 추가**

`core/models.py` `Order` 의 `original_quantity` 다음 줄에:
```python
    owner_strategy: str = ""  # 🆕 소유 전략명(TradingStock.owner_strategy_name).
                              # 빈 문자열 = 귀속 불가(레거시). 가드는 이때 폴백 + WARNING.
                              # 🔴 조회로 채우지 말 것 — 다중소유에서 임의 소유자를 집는다.
                              #    호출자가 실어 보낸다.
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_order_owner_strategy.py -v`
Expected: 2 passed

- [ ] **Step 5: `place_buy_order` / `place_sell_order` 에 인자 추가**

`core/orders/order_executor.py:46` 시그니처 끝에 `owner_strategy: str = ""` 추가.
`:237` `place_sell_order` 도 동일.

그리고 `Order(` 4곳에 `owner_strategy=owner_strategy,` 를 추가한다:
- `:118` `_execute_paper_buy_order` — 이 함수도 인자를 받아야 하므로 시그니처에 추가하고 `:98` 호출부에서 전달
- `:168` `_execute_real_buy_order` — 동일하게 시그니처 + `:104` 호출부
- `:287` `_execute_paper_sell_order` — 시그니처 + 호출부
- `:356` `_execute_real_sell_order` — 시그니처 + 호출부

재주문 2곳(`:513`·`:519`)은 **원 주문의 owner 를 승계**한다:
```python
                    new_order_id = await self.place_buy_order(
                        ..., owner_strategy=order.owner_strategy)
```

- [ ] **Step 6: 호출자가 넘기게 한다**

`core/trading/order_execution.py` — ⚠️ `trading_stock` 은 `with self.state_manager.lock:` **안**에 있고
`place_buy_order` 호출(`:229`)은 **밖**이다. **락 안에서 지역변수로 잡아 나온다:**

`:216` 근처(`trading_stock.is_buying = True` 옆)에 추가:
```python
                # 락 밖에서 쓸 owner 를 여기서 잡아 나간다 (trading_stock 은 락 안 객체).
                _owner = trading_stock.owner_strategy_name or ""
```
`:229` 를:
```python
            order_id = await self.order_manager.place_buy_order(
                stock_code, quantity, price, owner_strategy=_owner)
```
`:366` 매도도 같은 방식으로 `owner_strategy=` 를 추가한다(그 함수의 락 블록 안에서 `_owner` 를 잡을 것).

- [ ] **Step 7: 전달 테스트 추가**

```python
# tests/test_order_owner_strategy.py 에 추가
import asyncio
from unittest.mock import MagicMock


def test_place_buy_order_puts_owner_on_order(monkeypatch):
    """🔑 「기본값이 falsy 인 keyword 인자」는 이 프로젝트가 6번 당한 형태다.
    실제로 Order 에 실리는지 «값으로» 단언한다."""
    from core.orders import order_executor as oe

    captured = {}

    class Fake(oe.OrderExecutorMixin):
        def __init__(self):
            self.completed_orders = []
            self.logger = MagicMock()
            self.config = MagicMock(paper_trading=True)
            self.fund_manager = None

        def _get_current_3min_candle_time(self):
            return None

        async def _save_paper_buy_to_db(self, *a, **kw):
            captured["saved"] = True

    f = Fake()
    asyncio.get_event_loop().run_until_complete(
        f._execute_paper_buy_order("005930", 10, 70000, 0.1, 0.05,
                                   owner_strategy="rs_leader"))
    assert f.completed_orders[-1].owner_strategy == "rs_leader"
```

- [ ] **Step 8: 실행 + 커밋**

Run: `python -m pytest tests/test_order_owner_strategy.py -v`
Expected: 3 passed

```bash
git add core/models.py core/orders/order_executor.py core/trading/order_execution.py tests/test_order_owner_strategy.py
git commit -m "feat(orders): 주문에 소유 전략을 싣는다 — 가드 3개가 죽은 공통 뿌리"
```

---

## Task 3: owner 소비 — 🔴 엔트리 누수 재현하고 막는다

**Files:**
- Modify: `core/orders/order_monitor.py:370`·`:396`
- Modify: `core/orders/order_timeout.py:294`
- Test: `tests/test_position_entry_leak.py`

**Interfaces:**
- Consumes: `Order.owner_strategy` (Task 2)
- Produces: (없음 — 기존 `add_position`/`release_investment` 호출을 채울 뿐)

- [ ] **Step 1: 🔴 누수를 «재현»하는 테스트 (코드 주석의 주장을 사실로 확인)**

```python
# tests/test_position_entry_leak.py
from core.fund_manager import FundManager


def test_owner_mismatch_leaks_entry_forever():
    """🔴 order_monitor.py:361-369 의 blocker 주석을 실제로 재현한다.
    매수가 owner=None 으로 등록하고 매도가 owner 지정으로 지우면 엔트리가 남는다.
    남으면 len(codes) 가 단조 증가해 can_add_position 이 영구히 막힌다."""
    fm = FundManager(initial_funds=10_000_000)
    fm.add_position("005930")                      # 실주문 체결 경로 (owner 없음)
    fm.remove_position("005930", "elder_ema_pullback")   # liquidation (owner 지정)
    assert len(fm.current_position_codes) == 1, "재현 실패 — 전제를 다시 확인할 것"


def test_owner_roundtrip_leaves_nothing():
    """owner 를 양쪽에 채우면 짝이 맞아 깨끗이 지워진다."""
    fm = FundManager(initial_funds=10_000_000)
    fm.add_position("005930", "elder_ema_pullback")
    fm.remove_position("005930", "elder_ema_pullback")
    assert len(fm.current_position_codes) == 0, "owner 를 맞췄는데도 엔트리가 남는다"
```

- [ ] **Step 2: 재현 확인**

Run: `python -m pytest tests/test_position_entry_leak.py -v`
Expected: **둘 다 PASS.** 첫 테스트가 PASS 하면 **누수가 실재한다는 뜻**이다
(엔트리가 1건 남는 것을 단언하고 있다). 🔴 첫 테스트가 FAIL 하면 **주석의 전제가 틀린 것**이므로
**멈추고 보고할 것** — 그 경우 Task 3 의 근거가 사라진다.

- [ ] **Step 3: owner 를 넘긴다 (3곳)**

`core/orders/order_monitor.py:370`:
```python
                    self.fund_manager.add_position(order.stock_code, order.owner_strategy or None)
```
같은 파일 `:396`:
```python
                    self.fund_manager.release_investment(
                        buy_cost, stock_code=order.stock_code,
                        owner=order.owner_strategy or None)
```
`core/orders/order_timeout.py:294`:
```python
                self.fund_manager.add_position(order.stock_code, order.owner_strategy or None)
```

⚠️ `order_monitor.py:361-369` 의 blocker 주석은 **해소됐으므로 갱신**한다 —
지우지 말고 *"2026-08-13 해소: Order.owner_strategy 로 전달"* 를 덧붙인다.
🔑 ***왜 그렇게 됐는지의 기록이 사라지면 다음 사람이 같은 자리에서 되돌린다.***

- [ ] **Step 4: 통합 테스트 추가**

```python
# tests/test_position_entry_leak.py 에 추가
from datetime import datetime
from unittest.mock import MagicMock
from core.models import Order, OrderType


def test_monitor_registers_with_owner():
    """실주문 체결 경로가 owner 를 채워 등록해야 한다."""
    fm = FundManager(initial_funds=10_000_000)
    order = Order(order_id="O1", stock_code="005930", order_type=OrderType.BUY,
                  price=70000, quantity=10, timestamp=datetime.now(),
                  owner_strategy="rs_leader")
    # order_monitor 가 하는 일과 동일한 호출
    fm.add_position(order.stock_code, order.owner_strategy or None)
    assert ("005930", "rs_leader") in fm._position_entries
    # liquidation 이 owner 지정으로 지워도 이제 짝이 맞는다
    fm.remove_position("005930", "rs_leader")
    assert len(fm.current_position_codes) == 0
```

- [ ] **Step 5: 실행 + 커밋**

Run: `python -m pytest tests/test_position_entry_leak.py -v`
Expected: 3 passed

```bash
git add core/orders/order_monitor.py core/orders/order_timeout.py tests/test_position_entry_leak.py
git commit -m "fix(orders): 실주문 경로가 owner 를 안 넘겨 포지션 엔트리가 영구 잔류했다"
```

---

## Task 4: 예약 꼬리표 + `_invested_by_strategy` 감소 3경로

**Files:**
- Modify: `core/fund_manager.py` — `__init__:184` · `reserve_funds:260` · `confirm_order:309` · `cancel_order:390` · `release_investment:411` · `transfer_reservation:376`
- Test: `tests/test_fund_manager_strategy_accounting.py`

**Interfaces:**
- Consumes: (없음)
- Produces:
  - `self._reservation_owner: Dict[str, str]`
  - `get_invested_by_strategy(strategy_name: str) -> float` (테스트·리포트용 읽기 접근자)

- [ ] **Step 1: 실패하는 테스트 — 감소 대칭**

```python
# tests/test_fund_manager_strategy_accounting.py
from core.fund_manager import FundManager


def _fm():
    fm = FundManager(initial_funds=100_000_000,
                     strategy_max_pct_provider=lambda s: 0.20)
    return fm


def test_cancel_restores_strategy_invested():
    """🔴 예약 취소가 전략별 누적을 되돌려야 한다. 지금은 안 뺀다."""
    fm = _fm()
    assert fm.reserve_funds("O1", 1_000_000, strategy_name="rs_leader") is True
    assert fm.get_invested_by_strategy("rs_leader") == 1_000_000
    fm.cancel_order("O1")
    assert fm.get_invested_by_strategy("rs_leader") == 0, "취소했는데 누적이 남았다"


def test_confirm_adjusts_for_partial_fill():
    """예약 100만인데 90만만 체결되면 전략 누적도 90만이어야 한다."""
    fm = _fm()
    fm.reserve_funds("O2", 1_000_000, strategy_name="rs_leader")
    fm.confirm_order("O2", 900_000)
    assert fm.get_invested_by_strategy("rs_leader") == 900_000


def test_full_lifecycle_returns_to_zero():
    """🔑 대칭 단언 — 예약→체결→매도회수 한 바퀴 돌면 정확히 0."""
    fm = _fm()
    fm.reserve_funds("O3", 1_000_000, strategy_name="rs_leader")
    fm.confirm_order("O3", 1_000_000)
    fm.add_position("005930", "rs_leader")
    fm.release_investment(1_000_000, stock_code="005930", owner="rs_leader")
    assert fm.get_invested_by_strategy("rs_leader") == 0


def test_never_goes_negative_and_warns(caplog):
    """🔴 음수를 0 으로 조용히 뭉개면 「감소가 두 번 돌았다」는 사실이 사라진다."""
    fm = _fm()
    fm.reserve_funds("O4", 500_000, strategy_name="rs_leader")
    fm.confirm_order("O4", 500_000)
    fm.release_investment(500_000, stock_code="005930", owner="rs_leader")
    with caplog.at_level("WARNING"):
        fm.release_investment(500_000, stock_code="005930", owner="rs_leader")
    assert fm.get_invested_by_strategy("rs_leader") == 0
    assert any("전략별 투자 누적" in r.message or "음수" in r.message
               for r in caplog.records), "음수 시도가 조용히 넘어갔다"
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_fund_manager_strategy_accounting.py -v`
Expected: FAIL — `AttributeError: 'FundManager' object has no attribute 'get_invested_by_strategy'`

- [ ] **Step 3: 구현**

`__init__` 의 `self._invested_by_strategy` 다음 줄:
```python
        # order_id -> strategy_name. order_reservations 와 «같은 락 아래» 원자적으로 움직인다.
        # 🔴 order_reservations 를 튜플로 바꾸지 않는 이유: has_reservation 이
        #    .get(order_id, 0) > 0 으로 숫자를 가정하고 읽는 곳이 14군데다.
        self._reservation_owner: Dict[str, str] = {}
```

`reserve_funds` 의 전략 누적 부분(`:302-305`)을:
```python
            if strategy_name:
                self._reservation_owner[order_id] = strategy_name
                self._invested_by_strategy[strategy_name] = (
                    self._invested_by_strategy.get(strategy_name, 0.0) + amount
                )
```

새 헬퍼 (같은 클래스 안):
```python
    def get_invested_by_strategy(self, strategy_name: str) -> float:
        """전략별 누적 투자액 (읽기 전용 접근자)."""
        with self._lock:
            return self._invested_by_strategy.get(strategy_name, 0.0)

    def _dec_strategy_invested(self, strategy_name: str, amount: float) -> None:
        """전략별 누적 감소. 🔴 음수는 0 으로 막되 «WARNING 을 남긴다».

        조용히 뭉개면 「감소 경로가 두 번 돌았다」는 사실이 사라진다.
        (호출자가 이미 self._lock 을 잡고 있다 — RLock 이라 재진입 가능)
        """
        if not strategy_name:
            return
        with self._lock:
            cur = self._invested_by_strategy.get(strategy_name, 0.0)
            new = cur - float(amount)
            if new < -0.5:  # 반올림 오차 허용
                self.logger.warning(
                    f"⚠️ [{strategy_name}] 전략별 투자 누적이 음수가 될 뻔했다: "
                    f"현재 {cur:,.0f} - 감소 {amount:,.0f} = {new:,.0f} → 0 으로 보정. "
                    f"감소 경로가 중복 호출됐을 수 있다."
                )
            self._invested_by_strategy[strategy_name] = max(0.0, new)
```

`cancel_order` 의 `del self.order_reservations[order_id]` 앞에:
```python
            owner = self._reservation_owner.pop(order_id, "")
            self._dec_strategy_invested(owner, reserved_amount)
```

`confirm_order` 의 `del self.order_reservations[order_id]` 뒤(차액 정산 근처):
```python
            owner = self._reservation_owner.pop(order_id, "")
            # 예약≠체결 차액만큼 전략 누적을 보정한다(예약 시 «예약액»으로 더했으므로).
            if owner and reserved_amount != actual_amount:
                self._dec_strategy_invested(owner, reserved_amount - actual_amount)
```

`release_investment` 의 `self.invested_funds -= amount` 뒤:
```python
            if owner:
                self._dec_strategy_invested(owner, amount)
```

`transfer_reservation` 의 `self.order_reservations[new_id] = amount` 뒤:
```python
            if old_id in self._reservation_owner:
                self._reservation_owner[new_id] = self._reservation_owner.pop(old_id)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_fund_manager_strategy_accounting.py -v`
Expected: 4 passed

- [ ] **Step 5: 호출자가 `strategy_name` 을 넘기게 한다 (3곳)**

- `core/orders/order_executor.py:90` → `reserve_funds(temp_reserve_id, reserve_amount, strategy_name=owner_strategy)`
- `bot/trading_analyzer.py:147` → `reserve_funds(_reserve_id, required_amount, strategy_name=<그 자리의 전략명>)`
  ⚠️ 그 함수가 이미 전략을 알고 있는지 **읽고 확인**할 것. 모르면 상위에서 받아 내려야 한다.
  🔴 **조회로 만들어내지 말 것.**
- `core/fund_manager.py:756` → 내부 위임이므로 `strategy_name` 을 그대로 전달

- [ ] **Step 6: 커밋**

```bash
git add core/fund_manager.py core/orders/order_executor.py bot/trading_analyzer.py tests/test_fund_manager_strategy_accounting.py
git commit -m "fix(fund): 전략별 투자 누적에 감소 경로 3개 — 더하기만 있고 뺄 수가 없는 구조였다"
```

---

## Task 5: 자금 상한 섀도우 모드 + provider 주입

**Files:**
- Modify: `core/fund_manager.py` — `__init__` · `reserve_funds:276`
- Modify: `main.py:117`
- Test: `tests/test_fund_manager_shadow_cap.py`

**Interfaces:**
- Consumes: Task 4
- Produces:
  - `FundManager(..., strategy_cap_enforce: bool = False)`
  - `get_cap_shadow_stats() -> dict` — `{"would_block": {strategy: n}, "attempts": int}`

- [ ] **Step 1: 실패하는 테스트**

```python
# tests/test_fund_manager_shadow_cap.py
from core.fund_manager import FundManager


def _fm(enforce):
    return FundManager(initial_funds=10_000_000,
                       strategy_max_pct_provider=lambda s: 0.10,   # 상한 100만
                       strategy_cap_enforce=enforce)


def test_shadow_does_not_block():
    """🔑 섀도우는 판단은 하되 차단하지 않는다 — 페이퍼 동작 불변의 근거."""
    fm = _fm(enforce=False)
    assert fm.reserve_funds("A", 900_000, strategy_name="rs_leader") is True
    assert fm.reserve_funds("B", 900_000, strategy_name="rs_leader") is True  # 상한 초과인데 통과
    stats = fm.get_cap_shadow_stats()
    assert stats["would_block"].get("rs_leader") == 1
    assert stats["attempts"] == 2


def test_enforce_blocks():
    """결선 모드는 같은 입력을 거부한다."""
    fm = _fm(enforce=True)
    assert fm.reserve_funds("A", 900_000, strategy_name="rs_leader") is True
    assert fm.reserve_funds("B", 900_000, strategy_name="rs_leader") is False


def test_shadow_default_is_off():
    """🔴 기본이 섀도우가 아니면 실전 전환 첫날에 검증 안 된 가드가 처음 돈다."""
    fm = FundManager(initial_funds=10_000_000)
    assert fm.strategy_cap_enforce is False
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_fund_manager_shadow_cap.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'strategy_cap_enforce'`

- [ ] **Step 3: 구현**

`__init__` 시그니처에 `strategy_cap_enforce: bool = False` 추가하고 본문에:
```python
        # 🔴 기본은 «섀도우» — 판단은 하되 차단하지 않는다.
        #    이 프로젝트에는 정반대 실패가 둘 다 있었다: 「가드가 죽어 있던 것」 6번,
        #    「발효 첫날 처음 도는 가드」(2026-08-13 D1·D2). 섀도우는 그 사이다.
        self.strategy_cap_enforce: bool = strategy_cap_enforce
        self._cap_would_block: Dict[str, int] = {}
        self._cap_attempts: int = 0
```

`reserve_funds` 의 상한 블록(`:276-286`)을:
```python
            if strategy_name and self._strategy_max_pct_provider is not None and self.total_funds > 0:
                self._cap_attempts += 1
                max_pct = self._strategy_max_pct_provider(strategy_name)
                cap = self.total_funds * max_pct
                current = self._invested_by_strategy.get(strategy_name, 0.0)
                if current + amount > cap:
                    mode = "차단" if self.strategy_cap_enforce else "섀도우(통과)"
                    self.logger.info(
                        f"[{strategy_name}] 전략별 자금 상한 초과({mode}): "
                        f"현재투자 {current:,.0f}원 + 요청 {amount:,.0f}원 > 상한 {cap:,.0f}원 "
                        f"({max_pct:.0%})"
                    )
                    self._cap_would_block[strategy_name] = (
                        self._cap_would_block.get(strategy_name, 0) + 1)
                    if self.strategy_cap_enforce:
                        return False
```

새 접근자:
```python
    def get_cap_shadow_stats(self) -> dict:
        """자금 상한 섀도우 집계. 분모는 «상한 판정을 거친 매수 시도»다.
        ⚠️ K 한도(get_k_shadow_stats)와 분모가 다르니 섞어 세지 말 것."""
        with self._lock:
            return {"would_block": dict(self._cap_would_block),
                    "attempts": self._cap_attempts,
                    "enforce": self.strategy_cap_enforce}
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_fund_manager_shadow_cap.py -v`
Expected: 3 passed

- [ ] **Step 5: provider 를 «생성자」가 아니라 «setter」로 주입한다**

🔴 **실측(2026-08-13): `strategies/config.py` 에 `get_strategy_max_capital_pct` 같은 함수는 없다.**
`max_capital_pct` 는 전략 **인스턴스 속성**이다(`config.py:447` `instance.max_capital_pct = ...`).
그리고 `main.py:117` 은 전략 로드 **전에** `FundManager` 를 만든다 ⇒ **생성자 주입은 순서 문제를 만든다.**

⇒ **`initializer` 에서 K 주입과 «같은 자리」에 setter 로 넣는다.** `main.py` 는 손대지 않는다.

`core/fund_manager.py` 에 setter 추가:
```python
    def set_strategy_max_pct_provider(self, provider: Optional[Callable[[str], float]]) -> None:
        """전략명 → max_capital_pct 콜백 주입 (봇 초기화가 전략 로드 후 호출).

        🔴 생성자 주입이 아닌 이유: main.py:117 이 «전략 로드 전」에 FundManager 를
           만든다. 생성자에 넣으려면 그때 이미 전략 인스턴스가 있어야 하는데 없다.
        """
        with self._lock:
            self._strategy_max_pct_provider = provider
            self.logger.info(
                f"전략별 자금 상한 provider 주입: {'있음' if provider else '없음'} "
                f"(enforce={self.strategy_cap_enforce})")
```

`bot/initializer.py:509` — `self._apply_total_k_position_limit(k_by_strategy, unknown_k)` **바로 앞**에
넣는다. 그 스코프의 지역변수 **`strategies`**(전략 인스턴스 dict, `:501` 에서 `strategies.keys()` 로
쓰이는 그것)가 provider 의 출처다:

```python
        # 전략별 자금 상한 provider 주입 (2026-08-13). 미주입이면 상한이 통째로 죽는다
        # — 게이트(core/fund_manager.py:276)가 `provider is not None` 을 요구한다.
        # 🔴 기본이 섀도우이므로 주입해도 매매 동작은 안 바뀐다.
        _fm = getattr(self.bot, 'fund_manager', None)
        if _fm is not None and hasattr(_fm, 'set_strategy_max_pct_provider'):
            _strats = strategies   # 위 루프가 순회한 전략 인스턴스 dict

            def _max_pct(name: str) -> float:
                s = _strats.get(name)
                return float(getattr(s, 'max_capital_pct', 1.0)) if s is not None else 1.0

            _fm.set_strategy_max_pct_provider(_max_pct)

        self._apply_total_k_position_limit(k_by_strategy, unknown_k)
```

- [ ] **Step 5b: `max_capital_pct` 가 «그 객체에» 실제로 있는지 확인**

`strategies/config.py:447` 은 `instance.max_capital_pct = ...` 로 설정한다. `initializer` 의
`strategies` 가 그 dict 와 같은 객체인지 **실행으로 확인**한다:

```bash
python -c "
import sys; sys.path.insert(0,'.')
from strategies.config import load_strategy_instances  # ⚠️ 실제 로더 함수명 확인
" 2>&1 | head -3
```
또는 더 확실하게 — 재기동 후 로그의 `전략별 자금 상한 provider 주입: 있음` 다음 줄에서
상한이 **1.0(기본값 fallback)이 아닌 실제 값**으로 찍히는지 본다.
🔴 ***전 전략이 1.0 이면 `getattr` 가 전부 빗나간 것이다*** — 그때는 `max_capital_pct` 를
들고 있는 진짜 객체를 찾아 `_strats` 를 바꾼다. **1.0 을 「설정이 그런가 보다」로 넘기지 말 것.**

- [ ] **Step 6: 커밋**

```bash
git add core/fund_manager.py main.py tests/test_fund_manager_shadow_cap.py
git commit -m "feat(fund): 전략별 자금 상한 섀도우 모드 + provider 주입 — 기본은 차단 안 함"
```

---

## Task 6: `can_add_position` owner 축 + K 한도 + K 섀도우

**Files:**
- Modify: `core/fund_manager.py:570` · `__init__`
- Modify: `bot/initializer.py:_apply_total_k_position_limit`
- Modify: `core/trading/order_execution.py:202`
- Test: `tests/test_fund_manager_position_k.py`

**Interfaces:**
- Consumes: Task 2·3
- Produces:
  - `FundManager(..., position_k_enforce: bool = False)`
  - `set_strategy_position_limits(k_by_strategy: Dict[str, int]) -> None`
  - `can_add_position(stock_code: str = "", owner: Optional[str] = None) -> bool`
  - `get_k_shadow_stats() -> dict`

- [ ] **Step 1: 실패하는 테스트**

```python
# tests/test_fund_manager_position_k.py
from core.fund_manager import FundManager


def _fm(enforce=False):
    fm = FundManager(initial_funds=100_000_000, max_position_count=100,
                     position_k_enforce=enforce)
    fm.set_strategy_position_limits({"A": 2, "B": 3})
    return fm


def test_k_shadow_does_not_block():
    fm = _fm(enforce=False)
    fm.add_position("001", "A"); fm.add_position("002", "A")
    assert fm.can_add_position("003", owner="A") is True          # K=2 초과인데 통과
    assert fm.get_k_shadow_stats()["would_block"].get("A") == 1


def test_k_enforce_blocks():
    fm = _fm(enforce=True)
    fm.add_position("001", "A"); fm.add_position("002", "A")
    assert fm.can_add_position("003", owner="A") is False


def test_no_cross_strategy_interference():
    """🔑 B안 정합 — A가 K를 채워도 B는 여전히 살 수 있어야 한다."""
    fm = _fm(enforce=True)
    fm.add_position("001", "A"); fm.add_position("002", "A")
    assert fm.can_add_position("003", owner="A") is False
    assert fm.can_add_position("003", owner="B") is True


def test_scale_in_is_owner_scoped():
    """🔴 분할매수 판정이 owner 축이다.
    A가 보유한 종목을 A가 더 사면 분할매수(True), B가 사면 B의 K를 먹는다."""
    fm = _fm(enforce=True)
    fm.add_position("001", "A"); fm.add_position("002", "A")
    assert fm.can_add_position("001", owner="A") is True   # A 의 분할매수
    fm.add_position("010", "B"); fm.add_position("011", "B"); fm.add_position("012", "B")
    assert fm.can_add_position("001", owner="B") is False  # B 는 K=3 소진 → 새 포지션 거부


def test_missing_owner_warns_and_falls_back(caplog):
    """owner 미지정은 귀속 불가다. 조용히 통과시키지 않는다."""
    fm = _fm(enforce=True)
    with caplog.at_level("WARNING"):
        fm.can_add_position("003")
    assert any("귀속" in r.message or "owner" in r.message for r in caplog.records)


def test_k_shadow_default_is_off():
    fm = FundManager(initial_funds=10_000_000)
    assert fm.position_k_enforce is False
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_fund_manager_position_k.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'position_k_enforce'`

- [ ] **Step 3: 구현**

`__init__` 에 `position_k_enforce: bool = False` 추가하고:
```python
        self.position_k_enforce: bool = position_k_enforce
        self._strategy_k: Dict[str, int] = {}
        self._k_would_block: Dict[str, int] = {}
        self._k_attempts: int = 0
```

```python
    def set_strategy_position_limits(self, k_by_strategy: Dict[str, int]) -> None:
        """전략별 보유 한도 K 주입. initializer 가 산출한 dict 를 그대로 받는다.
        ⚠️ K 미상 전략은 애초에 이 dict 에 없다(initializer 가 WARNING 후 제외)."""
        with self._lock:
            self._strategy_k = dict(k_by_strategy or {})
            self.logger.info(f"전략별 보유 한도 주입: {self._strategy_k}")

    def get_k_shadow_stats(self) -> dict:
        """K 한도 섀도우 집계. 분모는 «신규 종목 매수 시도»다(분할매수 제외).
        ⚠️ 자금 상한(get_cap_shadow_stats)과 분모가 다르니 섞어 세지 말 것."""
        with self._lock:
            return {"would_block": dict(self._k_would_block),
                    "attempts": self._k_attempts,
                    "enforce": self.position_k_enforce}
```

`can_add_position` 을 교체:
```python
    def can_add_position(self, stock_code: str = "",
                         owner: Optional[str] = None) -> bool:
        """새 포지션 추가 가능 여부.

        🔴 분할매수 판정이 «owner 축»이다(2026-08-13). 이전에는 전역 고유 코드
           집합을 봐서, A전략이 보유한 종목을 B전략이 K 소모 없이 살 수 있었다.
        🔴 K 한도는 기본이 «섀도우» — 판단만 하고 차단하지 않는다.
           2026-08-13 실측에서 세 전략이 이미 K 를 넘긴 상태였다
           (daytrading 8/5 · minervini 6/3 · ma20 6/5). 바로 켜면 셋이 즉시 멈춘다.
        """
        with self._lock:
            owner = owner or None

            if owner is None:
                self.logger.warning(
                    f"⚠️ can_add_position: owner 미지정 — 전략 귀속 불가로 전역 한도 폴백 "
                    f"({stock_code})")
                codes = self.current_position_codes
                if stock_code and stock_code in codes:
                    return True
                if len(codes) >= self.max_position_count:
                    self.logger.warning(
                        f"⚠️ 동시 보유 종목 수 초과: 현재 {len(codes)}개 "
                        f"/ 최대 {self.max_position_count}개")
                    return False
                return True

            # owner 축: 그 전략이 이미 보유 중인 종목이면 분할매수로 허용
            owned = {c for c, o in self._position_entries if o == owner}
            if stock_code and stock_code in owned:
                return True

            k = self._strategy_k.get(owner)
            if k is None:
                self.logger.warning(
                    f"⚠️ [{owner}] K 미상 — 전역 한도로 폴백 ({stock_code})")
                return len(self.current_position_codes) < self.max_position_count

            self._k_attempts += 1
            if len(owned) >= k:
                mode = "차단" if self.position_k_enforce else "섀도우(통과)"
                self.logger.warning(
                    f"⚠️ [{owner}] 보유 한도 초과({mode}): 현재 {len(owned)}종목 / K {k}")
                self._k_would_block[owner] = self._k_would_block.get(owner, 0) + 1
                if self.position_k_enforce:
                    return False
            return True
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest tests/test_fund_manager_position_k.py -v`
Expected: 6 passed

- [ ] **Step 5: K 주입 + 호출자 owner 전달**

`bot/initializer.py:_apply_total_k_position_limit` 의 `fund_manager.max_position_count = new_limit` 뒤:
```python
            # 전략별 K 를 fund_manager 에 주입 (2026-08-13). 전역 한도는 폴백으로만 남는다.
            if hasattr(fund_manager, "set_strategy_position_limits"):
                fund_manager.set_strategy_position_limits(k_by_strategy)
```

`core/trading/order_execution.py:202` 를:
```python
                if self.fund_manager and not self.fund_manager.can_add_position(
                        stock_code, owner=trading_stock.owner_strategy_name or None):
```

- [ ] **Step 6: 커밋**

```bash
git add core/fund_manager.py bot/initializer.py core/trading/order_execution.py tests/test_fund_manager_position_k.py
git commit -m "feat(fund): 보유 한도를 전략별 K 로 — 전역 축은 교차 간섭을 만든다(B안 충돌)"
```

---

## Task 7: EOD 리포트 2줄 + 진입점 실호출 + 회귀

**Files:**
- Modify: `tools/daily_trading_summary.py`
- Test: `tests/test_guards_wiring.py`

**Interfaces:**
- Consumes: Task 5·6
- Produces: (없음)

- [ ] **Step 1: 🔑 진입점 실호출 테스트**

```python
# tests/test_guards_wiring.py
from unittest.mock import MagicMock
from core.fund_manager import FundManager


def test_initializer_injects_both_provider_and_k():
    """🔑 이 결함 자체가 「인자를 안 넘겨서」 생겼다.
    소스 문자열 단언은 죽은 경로도 통과한다 — 초기화를 «실제로 돌려» 값으로 확인한다.

    진입점 = BotInitializer._apply_total_k_position_limit
    (실측 확인: bot/initializer.py:404 `class BotInitializer` · :407 `__init__(self, bot)`)."""
    from bot.initializer import BotInitializer

    fm = FundManager(initial_funds=10_000_000)
    bot = MagicMock()
    bot.fund_manager = fm
    init = BotInitializer(bot)

    init._apply_total_k_position_limit({"A": 2, "B": 3}, [])

    # K 가 «실제로» 들어갔는가
    assert fm._strategy_k == {"A": 2, "B": 3}, "K 가 주입되지 않았다"
    # 전역 한도도 정정됐는가 (기존 동작 유지)
    assert fm.max_position_count >= 5


def test_provider_injection_is_effective_not_just_present():
    """provider 가 «있다」가 아니라 «먹는다」를 단언한다.
    주입 후 상한 판정이 실제로 그 값을 쓰는지 본다."""
    fm = FundManager(initial_funds=10_000_000, strategy_cap_enforce=True)
    assert fm.reserve_funds("A1", 5_000_000, strategy_name="X") is True  # provider 없음 = 무제한

    fm2 = FundManager(initial_funds=10_000_000, strategy_cap_enforce=True)
    fm2.set_strategy_max_pct_provider(lambda name: 0.10)   # 상한 100만
    assert fm2.reserve_funds("A2", 5_000_000, strategy_name="X") is False, \
        "provider 를 주입했는데 상한이 안 먹는다"


def test_shadow_defaults_keep_paper_unchanged():
    """🔴 두 가드 모두 기본이 섀도우여야 페이퍼 동작이 0줄이다."""
    fm = FundManager(initial_funds=10_000_000)
    assert fm.strategy_cap_enforce is False
    assert fm.position_k_enforce is False


def test_two_shadow_counters_never_mix():
    """🔑 스펙 테스트 6d — 분모가 다르므로 카운터가 섞이면 안 된다.
    자금 상한만 초과했을 때 K 카운터는 0 이어야 한다."""
    fm = FundManager(initial_funds=10_000_000)
    fm.set_strategy_max_pct_provider(lambda name: 0.05)   # 상한 50만
    fm.set_strategy_position_limits({"X": 10})            # K 는 넉넉
    fm.reserve_funds("B1", 400_000, strategy_name="X")
    fm.reserve_funds("B2", 400_000, strategy_name="X")    # 상한 초과 (섀도우 통과)

    cap = fm.get_cap_shadow_stats()
    k = fm.get_k_shadow_stats()
    assert sum(cap["would_block"].values()) == 1, "자금 상한 카운터가 안 올랐다"
    assert sum(k["would_block"].values()) == 0, "K 카운터가 자금 상한 사건에 오염됐다"
    assert k["attempts"] == 0, "K 분모가 매수 시도로 오염됐다"
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest tests/test_guards_wiring.py -v`
Expected: **4 passed** (Task 5·6 를 마친 상태 기준).
🔴 `test_initializer_injects_both_provider_and_k` 가 FAIL 하면 **주입이 실제로 안 되는 것**이다 —
소스에 코드가 있어도 실패할 수 있고, 그게 이 테스트의 존재 이유다.

- [ ] **Step 3: EOD 리포트 2줄**

`tools/daily_trading_summary.py` 의 요약 출력부에:
```python
    # 🔴 N=0 이어도 «줄은 나와야 한다» — 줄이 없으면 「걸린 게 없다」가 아니라 「안 돌았다」다.
    cap = fund_manager.get_cap_shadow_stats()
    k = fund_manager.get_k_shadow_stats()
    cap_rate = (sum(cap["would_block"].values()) / cap["attempts"] * 100) if cap["attempts"] else 0.0
    k_rate = (sum(k["would_block"].values()) / k["attempts"] * 100) if k["attempts"] else 0.0
    logger.info("[전략상한 %s] 차단됐을 매수 %d건 / 시도 %d건 = %.1f%% · 내역 %s",
                "결선" if cap["enforce"] else "섀도우",
                sum(cap["would_block"].values()), cap["attempts"], cap_rate,
                cap["would_block"] or {})
    logger.info("[K한도 %s] 막혔을 신규매수 %d건 / 신규 시도 %d건 = %.1f%% · 내역 %s",
                "결선" if k["enforce"] else "섀도우",
                sum(k["would_block"].values()), k["attempts"], k_rate,
                k["would_block"] or {})
```
⚠️ 이 도구가 `fund_manager` 에 접근할 수 있는지 **먼저 읽어 확인**할 것. 못 하면
봇 종료 시점(`main.py` 의 EOD 훅)에서 찍는다. **접근 경로를 지어내지 말 것.**

- [ ] **Step 4: 회귀 — 실패 «집합» 차분**

```bash
git stash -u
python -m pytest -q 2>&1 | tail -5 > /tmp/base.txt
git stash pop
python -m pytest -q 2>&1 | tail -5 > /tmp/after.txt
diff /tmp/base.txt /tmp/after.txt
```
⚠️ repo 루트 + VS 번들 Python. 캡처가 teardown 에서 터지면 `--capture=no`.
Expected: **신규 실패 0**

- [ ] **Step 5: 커밋**

```bash
git add tools/daily_trading_summary.py tests/test_guards_wiring.py
git commit -m "feat(tools): 섀도우 2종 EOD 리포트 — N=0 이어도 줄은 나와야 한다"
```

- [ ] **Step 6: 완료 판정 체크리스트**

- [ ] 테스트 통과 — Task 2:3 · 3:3 · 4:4 · 5:3 · 6:6 · 7:4 = **23개** (스펙이 요구한 14개 전부 포함)
- [ ] 전체 스위트 실패 집합 **동일**
- [ ] 재기동 후 로그에 `전략별 보유 한도 주입: {...}` 확인
- [ ] EOD 리포트에 `[전략상한 섀도우]`·`[K한도 섀도우]` **두 줄** 확인
- [ ] 페이퍼 매수·매도 건수/금액 **무변경**(전일 대비 이상 없음)

---

## 5거래일 후 (구현 밖, 운영 절차)

**사전등록(2026-08-13, 사후 완화 없음)**: 두 차단율을 **각각** 산출해 **가드별로 따로** 판단한다.

| 가드 | 분모 | 결선 조건 |
|---|---|---|
| 전략별 자금 상한 | 상한 판정을 거친 **매수 시도** | X ≤ 10% → `strategy_cap_enforce=True` |
| 전략별 K 한도 | **신규 종목** 매수 시도 | X ≤ 10% → `position_k_enforce=True` |

- X > 10% ⇒ **결선하지 않는다.** 설정값(`max_capital_pct` / K) 자체를 재검토한다.
- K 섀도우 기간에 **초과 전략 셋**(`daytrading` 8/5 · `minervini` 6/3 · `ma20` 6/5)의 보유가
  K 아래로 내려오는지 기록한다. **안 내려오면 결선이 아니라 K 재검토가 답이다.**

## 범위 밖

- 🔴 **휴장일 실주문 검증** — 별도 절차 문서. 이 계획이 끝나야 검증 대상이 확정된다.
- 🔴 **`max_capital_pct`·K 값 자체의 적정성** — 섀도우 결과를 보고 별건으로.
- 🔴 **`liquidation_handler._force_complete_failed_stocks` 의 `is_virtual` 게이트 부재** —
  이 계획은 owner 를 채워 문제를 없애지만 게이트 부재 자체는 손대지 않는다.
