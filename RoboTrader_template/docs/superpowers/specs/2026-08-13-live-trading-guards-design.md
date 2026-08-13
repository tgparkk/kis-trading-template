# 실매매 전환 가드 결선 — 설계 (2026-08-13)

> **성격**: 실전 전환 blocker 해소. **페이퍼 매매 동작 0줄**(섀도우 모드가 기본).
> 실제로 달라지는 것은 **로그 몇 줄 + EOD 리포트 한 줄**뿐이다.
> ⚠️ 휴장일 실주문 검증은 **이 스펙 밖**이다(§11) — 코드가 아니라 절차이고, 이 스펙이 끝나야 대상이 확정된다.

---

## 0. 왜 지금

2026-08-13 EOD 점검에서 사장님이 *「실매매 전환 P1 3건부터 처리합시다」* 라고 지시했다.
코드를 열어보니 **3건이 아니라 4건**이었고, 그중 셋이 **같은 뿌리**를 공유한다.

### 세 가드가 죽은 이유가 같다

```
① 전략별 자금 상한   — 어느 전략이 이 주문의 주인인지 모른다 → 상한을 못 건다
② 전략별 보유 한도   — 어느 전략이 이 포지션의 주인인지 모른다 → K 를 못 센다
③ 포지션 엔트리 누수 — 어느 전략이 이 포지션의 주인인지 모른다 → 지울 짝을 못 찾는다
```

🔑 ***세 개가 다른 결함처럼 보였지만 하나의 부재다 — 「주문에 소유 전략이 실려 있지 않다」.***
그래서 이 스펙의 중심 변경은 **하나**이고 나머지는 그 결과다.

### 코드가 스스로 blocker 라고 적어둔 것 (`order_monitor.py:361-369`)

> *⚠️ 실전 전환 blocker: 이 경로는 페이퍼 모드에선 `pending_orders` 자체가 비어 휴면이라
> 무해하나, 실전 모드에선 `liquidation_handler._force_complete_failed_stocks`(is_virtual
> 게이트 없음)가 owner 지정 제거를 하므로 여기서 등록한 **owner=None 엔트리가 영구 잔류**할
> 수 있다. 실전 전환 전에 **주문→소유 전략 연결을 만들어 owner 를 전달**해야 한다.*

⚠️ **이건 코드 주석의 «주장»이지 우리가 측정한 사실이 아니다.** 구현 시 **재현 테스트로 먼저 확인**한다(§8-1).

🔴 **왜 치명적인가**: `(code, None)` 엔트리가 안 지워지면 `len(current_position_codes)` 가
**단조 증가**한다 ⇒ `can_add_position` 이 결국 **영구히 모든 신규 매수를 막는다**.
「한도 58을 60으로 올린다」로는 며칠 벌 뿐이다. **두더지잡기다.**

---

## 1. 결정 사항 (사장님 확정, 2026-08-13)

| # | 항목 | 결정 |
|---|---|---|
| 1 | 자금 상한 결선 방식 | **섀도우 모드 먼저** — 판단은 하되 차단은 안 한다 |
| 2 | 섀도우 출구 기준 | **5거래일 관측 · 차단율 ≤ 10% 면 결선** (사전등록, 사후 완화 없음) |
| 3 | 보유 한도 방향 | **주문→owner 연결 + 전략별 K 한도.** 전역 한도는 폴백·안전망으로만 |
| 4 | **K 한도도 섀도우로 시작** | §6 측정에서 **세 전략이 이미 K 초과**로 드러나 추가된 결정 |
| 5 | 분할매수 판정 축 | **owner 축으로 변경** — 측정 영향 **2.1%(1종목)** 확인 후 승인 |
| 6 | 휴장일 실주문 검증 | **별도 절차 문서**(이 스펙 밖) |

### 관리자가 결정한 것 (구현 세부 — 매매 동작 무관)

- **`_reservation_owner` 병렬 dict** 를 쓴다. `order_reservations` 를 튜플로 바꾸지 않는다.
  이유 = ①`fund_manager` 안에 두면 **기존 `self._lock`(RLock) 아래에서 금액과 전략 꼬리표가
  원자적으로 같이 움직인다**(별도 맵을 `order_manager` 에 두면 상태가 갈라져 한쪽만 갱신되는
  순간 지금과 같은 결함이 재발한다) ②튜플로 바꾸면 `has_reservation:388` 의
  `.get(order_id, 0) > 0` 이 **`TypeError`** 로 깨진다(읽는 곳 14군데).

---

## 2. 실측 진단 (2026-08-13 코드 확인)

### 2.1 전략별 자금 상한 — 이중으로 죽어 있다

게이트 (`core/fund_manager.py:276`):
```python
if strategy_name and self._strategy_max_pct_provider is not None and self.total_funds > 0:
```

| 겹 | 사실 |
|---|---|
| ① provider 미주입 | `main.py:117` = `FundManager(max_daily_loss_ratio=_max_daily_loss)` — 인자 없음 ⇒ `None` |
| ② `strategy_name` 미전달 | 호출자 **3곳 전부** 기본값 `""`(falsy) — `fund_manager.py:756` · `order_executor.py:90` · `bot/trading_analyzer.py:147` |

🔑 ***②가 먼저 걸리므로 provider 만 주입해도 안 돈다. 두 겹을 다 고쳐야 한다.***
🆕 이건 「죽은 가드」 새 형태 = **「기본값이 falsy 인 keyword-only 가드 인자」** — grep 으로 안 잡힌다.

### 2.2 `_invested_by_strategy` — 감소 경로가 «구조적으로» 없다

`core/fund_manager.py` 전수: 초기화(`:187`) · 읽기(`:279`) · **더하기(`:303-305`)** 뿐이고 **빼는 곳이 0**.

🔑 ***그런데 더 깊은 문제는 「빼는 코드를 안 썼다」가 아니라 「뺄 수가 없다」는 것이다.***
`order_reservations: Dict[str, float]`(`:184`)가 **금액만** 들고 있어서
`cancel_order(order_id)`·`confirm_order(order_id)` 시점에 **그 주문이 어느 전략 것인지 알 수 없다.**

🟢 **매도 쪽은 이미 풀려 있다** — `release_investment(amount, stock_code, owner)`(`:411`)의
**`owner` 가 곧 전략명**이다(docstring: *"소유 전략 표기 (슬롯 객체의 owner_strategy_name)"*).

### 2.3 보유 한도 — 버그가 아니라 알려진 아키텍처 충돌

`can_add_position`(`:570`)은 **전역** 카운트를 본다. `max_position_count` 기본 **20**이고
`bot/initializer.py:_apply_total_k_position_limit`(`:511`)가 `max(20, ΣK)` = **58** 로 정정한다.

`initializer.py:520-525` 원문:
> *⚠️ 이 값을 페이퍼 매수 경로에 결선하지 말 것 — 한도를 실제로 강제하는 `can_add_position()` 은
> `core/trading/order_execution.py` 의 **실주문 경로에만** 결선돼 있고, 그대로 두는 것이 사장님
> 결정(2026-07-29)이다. 전역 한도는 2026-06-16 채택한 **전략별 완전독립 포지션(B안)** 설계와
> 충돌한다 — 먼저 채운 전략이 나머지 전략을 굶기는 교차 간섭이 생긴다.*

⇒ **전역 한도를 실전에서 강제하는 것 자체가 B안과 어긋난다.** 값을 올리는 게 아니라 **축을 바꿔야** 한다.

### 2.4 owner 전달 현황 — 복원은 되고 실주문은 안 된다

| 경로 | 호출 | owner |
|---|---|---|
| 복원 | `state_restorer.py:247` `add_position(stock_code, owner)` | 🟢 **있다** |
| 실주문 체결 | `order_monitor.py:370` `add_position(order.stock_code)` | 🔴 **없다** |
| 주문 타임아웃 | `order_timeout.py:294` `add_position(order.stock_code)` | 🔴 **없다** |
| 실주문 매도 회수 | `order_monitor.py:396` `release_investment(buy_cost, stock_code=...)` | 🔴 **없다** |

🟢 **개념은 이미 있다** — `TradingStock.owner_strategy_name`(`core/models.py:169`).
**새로 만드는 게 아니라 주문까지 실어 나르기만 하면 된다.**

🟢 **변경 면적도 작다** — `Order` 는 `core/models.py:90` 한 곳에 정의돼 있고
생성 지점이 **`core/orders/order_executor.py` 4곳뿐**(`:118`·`:168`·`:287`·`:356`).

---

## 3. 설계 — 중심 변경 하나

### 3.1 `Order` 에 소유 전략을 싣는다

`core/models.py` `Order` 에 필드 하나:
```python
owner_strategy: str = ""   # 소유 전략명. TradingStock.owner_strategy_name 에서 채운다.
                           # 빈 문자열 = 귀속 불가(레거시). 가드는 이때 폴백 + WARNING.
```

`order_executor.py` 4곳에서 `TradingStock.owner_strategy_name` 을 읽어 채운다.

**경계**: `fund_manager` 는 여전히 «금액과 엔트리»만 안다. 전략이 무엇인지는 **문자열 꼬리표**로만
받고 **해석하지 않는다**. 전략 지식은 `order_executor`·`initializer` 에 남는다.

### 3.2 예약에 전략 꼬리표 (`fund_manager`)

```python
self._reservation_owner: Dict[str, str] = {}   # order_id -> strategy_name
```
`reserve_funds` 에서 `strategy_name` 이 있으면 같이 기록하고,
`cancel_order`·`confirm_order`·`transfer_reservation` 에서 같이 옮기거나 지운다.

### 3.3 감소 경로 3개

| 시점 | 지금 | 추가 |
|---|---|---|
| `cancel_order`(`:390`) | 예약만 환불 | `_invested_by_strategy[owner] -= reserved_amount` |
| `confirm_order`(`:309`) | 예약→투자 이동 | 예약≠체결 **차액(`diff`)만큼** 조정 |
| `release_investment`(`:411`) | 투자 회수 | `_invested_by_strategy[owner] -= amount` (owner 는 인자에 이미 있다) |

⚠️ **음수 방지 + 음수가 나오면 WARNING.**
🔑 ***조용히 0 으로 뭉개면 「감소 경로가 두 번 돌았다」는 사실이 사라진다*** — 이 프로젝트가
반복해서 당한 형태다(가드가 조용히 무력화되고 경보로 안 잡힘).

### 3.4 owner 를 실제로 넘긴다

```
order_monitor.py:370   add_position(code)                     → add_position(code, order.owner_strategy)
order_timeout.py:294   add_position(code)                     → add_position(code, order.owner_strategy)
order_monitor.py:396   release_investment(cost, stock_code=)  → + owner=order.owner_strategy
```

🔴 **이것이 「엔트리 영구 잔류」의 실제 수정이다.**

---

## 4. 섀도우 모드 ① — 전략별 **자금** 상한

> 🔁 **보유 K 한도의 섀도우는 §5.1 에 따로 있다.** 둘은 분모가 다르므로 카운터를 섞지 않는다.

```python
FundManager(..., strategy_cap_enforce: bool = False)   # 기본 = 섀도우
```

`reserve_funds` 의 상한 체크가 초과를 만나면:

| 모드 | 동작 |
|---|---|
| **섀도우**(기본) | WARNING + `_cap_would_block[strategy] += 1` · **통과시킨다** |
| **결선**(`True`) | 지금처럼 `return False` |

두 모드 모두 **판단 자체는 실행한다** — 배선이 살아 있는지 섀도우에서 확인된다.
🔑 ***이 프로젝트에는 정반대 실패가 둘 다 있었다*** — 「가드가 죽어 있던 것」 6번,
「발효 첫날 처음 도는 가드」(D1·D2). 섀도우는 그 사이다.

**EOD 리포트에 한 줄 추가**:
```
[전략상한 섀도우] 차단됐을 매수 N건 / 총 매수 시도 M건 = X.X%  (전략별 내역: ...)
```

### 🔴 사전등록 — 결선 조건 (2026-08-13 확정, 사후 완화 없음)

- **5거래일** 관측 후 **X ≤ 10%** ⇒ `strategy_cap_enforce=True` 로 결선.
- **X > 10%** ⇒ **결선하지 않는다.** `max_capital_pct` 설정값 자체를 재검토한다
  (상시 매수중단이 된다는 뜻이므로 가드가 아니라 설정이 틀린 것이다).
- ⚠️ ***숫자를 본 뒤 기준을 늘리지 않는다.*** 시총 게이트 v2 가 정확히 그 방식으로 폐기됐다.

⚠️ **섀도우가 알려주지 못하는 것**: 「얼마나 자주 걸리는가」는 알려주지만 **「그 상한값이 옳은가」는
안 알려준다**. 차단율이 낮게 나와도 그건 *이 국면에서 안 걸렸다* 일 뿐이다 — 결선 후에도 계속 봐야 한다.

**참고 수치(메모리 출처, 오늘 재측정 안 함)**: 결선 시 `rs_leader` 8,808,423 · `deep_mr` 7,550,077
로 현재 `VirtualTradingManager` 1천만 격리보다 **빡빡해진다**. 구현 시 재측정할 것.

---

## 5. 전략별 K 보유 한도

```python
can_add_position(stock_code: str = "", owner: Optional[str] = None) -> bool
```

| 입력 | 판정 |
|---|---|
| **그 owner 가** 이미 보유 중인 종목 | `True` (분할매수, 기존 의도 유지) |
| `owner` 있음 | **그 전략의 엔트리 수 vs 그 전략의 K**. 다른 전략은 영향 없음 |
| `owner` 없음 | 🔴 **WARNING**(귀속 불가) + **전역 한도로 폴백** |

🔴 **첫 줄이 기존 코드와 뜻이 달라지는 지점이다 — 의도적이다.**
지금은 `stock_code in codes`(**전역 고유 코드 집합**)라 *A전략이 보유한 종목을 B전략이 사면
분할매수로 오인돼 K 를 안 먹고 통과*한다. owner 축으로 바꾸면 **B에게는 새 포지션**이므로
B의 K 를 먹어야 맞다. ⚠️ 이 변경은 **실주문 경로에서만** 유효하다(페이퍼는 결선 안 돼 있음).
바뀌는 방향은 **조이는 쪽**이므로 §8 에 전용 테스트를 둔다.

🔑 **전략별 K 가 hard gate 가 되면 총합은 자동으로 ΣK 를 넘지 못한다** ⇒ 폭주 방지가 구조적으로
따라온다. 전역 한도는 **폴백·안전망**으로만 남는다(값은 지금처럼 `max(기존, ΣK)`).

🟢 **B안 정합**: A전략이 K 를 채워도 B전략은 여전히 매수 가능 ⇒ **교차 간섭 0**.

### 5.1 🔴 K 한도도 섀도우로 시작한다 (2026-08-13 결정)

§6 측정으로 **세 전략이 이미 K 를 넘긴 상태**임이 드러났다. 바로 켜면 그 셋이 즉시 멈춘다.

```python
FundManager(..., position_k_enforce: bool = False)   # 기본 = 섀도우
```

| 모드 | `can_add_position` 동작 |
|---|---|
| **섀도우**(기본) | K 초과여도 **`True` 반환** + WARNING + `_k_would_block[strategy] += 1` |
| **결선**(`True`) | K 초과 시 `False` |

**출구 기준은 자금 상한과 동일**(5거래일 · 차단율 ≤10%). ⚠️ 단 **판정 분모가 다르다** —
자금 상한은 «매수 시도», K 한도는 «신규 종목 매수 시도»다. **섞어 세지 말 것.**

🔑 **섀도우 기간에 같이 볼 것**: 초과 전략 셋(`daytrading` 8/5 · `minervini` 6/3 · `ma20` 6/5)의
보유가 **자연 감소해 K 아래로 내려오는가**. 내려오면 결선 시 충격이 없고, 안 내려오면
**K 값 자체가 실제 운용과 안 맞는다는 뜻**이므로 결선이 아니라 K 재검토가 답이다.

EOD 리포트 한 줄 추가:
```
[K한도 섀도우] 막혔을 신규매수 N건 / 신규 시도 M건 = X.X%  ·  K초과 전략: daytrading(8/5) ...
```

**K 의 출처**: `initializer._apply_total_k_position_limit` 이 이미 `k_by_strategy` 를 계산한다.
그 dict 를 `fund_manager` 에 주입한다(`set_strategy_position_limits(k_by_strategy)`).
⚠️ **K 미상 전략은 합계에서 제외하고 WARNING** — 기존 가드와 같은 규약. 조용히 0 으로 세지 않는다.

---

## 6. ✅ 선행 측정 완료 (2026-08-13) — **K 한도는 이미 새고 있다**

아침의 「보유 60 > ΣK 58」이 풀렸다. `virtual_trading_records` 미청산 포지션 전수
(BUY 중 그 뒤 같은 `(stock_code, strategy)` SELL 이 없는 것):

| | 값 |
|---|--:|
| 미청산 엔트리 `(code, strategy)` | **48** |
| 고유 종목 | **47** |
| **2개 이상 전략이 겹쳐 보유한 종목** | **1** (`003280` = ma5 + minervini) = **2.1%** |

### 🔴 전략 셋이 이미 자기 K 를 넘겼다

| 전략 | 현재 보유 | K | |
|---|--:|--:|---|
| `daytrading_3methods_breakout` | **8** | 5 | 🔴 **+3 (160%)** |
| `minervini_volume_dryup` | **6** | 3 | 🔴 **+3 (200%)** |
| `book_pullback_ma20` | **6** | 5 | 🔴 +1 |
| `book_envelope_200d` | 5 | 5 | 꽉 참 |
| `elder_ema_pullback` | 16 | 20 | 여유 4 |
| `rs_leader` | 4 | 10 | 여유 6 |
| `book_pullback_ma5` | 3 | 5 | 여유 2 |
| `deep_mr_dev20` | 0 | 5 | 여유 5 |
| **합계** | **48** | **58** | |

🔑 ***합계는 58 아래인데 개별 전략 셋이 넘겼다.*** 그래서 「ΣK 58 vs 보유 60」이라는 «전역» 비교로는
보이지 않았다. **전역 지표가 개별 위반을 가린 전형적 사례다.**

**원인은 명확하다** — `can_add_position` 이 **페이퍼 매수 경로에 결선돼 있지 않아**
(2026-07-29 의도된 결정) 페이퍼는 K 를 한 번도 지킨 적이 없다.

### ⚠️ 이 사실이 설계를 바꾼다

***전략별 K 를 실전에서 바로 켜면 `daytrading`·`minervini`·`ma20` 세 전략이 즉시 멈춘다***
(기존 보유분은 유지되지만 신규 매수 0). 그리고 그게 「가드가 제대로 도는 것」인지 「설정이 틀린 것」인지
**구분이 안 된다** — 2026-08-13 아침 D1·D2 발효 때와 같은 상황이 된다.

⇒ **K 한도도 섀도우로 시작한다**(§5.1). 사장님 결정(2026-08-13).

⚠️ **아직 안 잰 것**: `owner=None` 엔트리의 존재 여부. 위 측정은 DB(`virtual_trading_records`)
기준이고 `fund_manager._position_entries`(런타임 메모리) 기준이 아니다. **구현 Task 1 에서
런타임 엔트리도 같은 방식으로 찍어 대조할 것** — 두 값이 다르면 그 차이가 곧 누수다.

---

## 7. 데이터 흐름

```
매수 결정 (전략)
  └─ order_executor: Order(owner_strategy=TradingStock.owner_strategy_name)
       ├─ fund_manager.reserve_funds(oid, amt, strategy_name=owner)
       │    ├─ 상한 초과? → 섀도우: WARNING+카운터, 통과 / 결선: 거부
       │    ├─ _reservation_owner[oid] = owner
       │    └─ _invested_by_strategy[owner] += amt
       ├─ (실주문) order_execution: can_add_position(code, owner=owner)
       └─ 체결 → order_monitor
            ├─ fund_manager.confirm_order(oid, actual)   → 차액만큼 _invested_by_strategy 조정
            └─ fund_manager.add_position(code, owner)     ← 🔴 지금 비어 있는 곳

매도 체결 → order_monitor
  └─ fund_manager.release_investment(cost, stock_code=code, owner=owner)
       ├─ _invested_by_strategy[owner] -= cost
       └─ remove_position(code, owner)                    ← 짝이 맞아 엔트리가 지워진다

주문 취소 → fund_manager.cancel_order(oid)
  └─ _invested_by_strategy[_reservation_owner[oid]] -= reserved
```

---

## 8. 테스트 (전부 red 먼저)

| # | 무엇 | red 조건 |
|---|---|---|
| 1 | 🔴 **교차 경로 누수 재현** — `add_position(code)`(owner 없음) → `remove_position(code, owner)` → **엔트리 잔류** | 수정 전 잔류 1, 수정 후 **0** |
| 2 | **감소 대칭 ①** — `reserve → cancel` 후 `_invested_by_strategy` **원복** | 지금은 안 줄어듦 |
| 3 | **감소 대칭 ②** — `reserve → confirm(예약≠체결) → release` 후 **정확히 0** | 차액 조정 없음 |
| 4 | 🔑 **교차 간섭 없음** — A전략이 K 를 채워도 **B전략은 매수 가능** | 전역 한도면 B도 막힘 |
| 5 | **자금상한 섀도우가 차단 안 함** — 상한 초과인데 `reserve_funds` 가 `True` + 카운터 1 | |
| 6 | **자금상한 결선 모드가 차단함** — 같은 입력에 `strategy_cap_enforce=True` 면 `False` | |
| 6b | **K 섀도우가 차단 안 함** — K 초과인데 `can_add_position` 이 `True` + 카운터 1 | |
| 6c | **K 결선 모드가 차단함** — 같은 입력에 `position_k_enforce=True` 면 `False` | |
| 6d | 🔑 **두 섀도우 카운터가 섞이지 않는다** — 자금상한 초과만 났을 때 K 카운터는 **0** (분모가 다르다) | |
| 7 | **owner 미지정 폴백** — `can_add_position(code)` 가 WARNING + 전역 한도 판정 | |
| 7b | 🔴 **분할매수 판정이 owner 축** — A가 보유한 종목을 **B가** 살 때 B의 K 를 먹는다(K 소진 시 `False`), **A가** 살 때는 분할매수로 `True` | 지금은 둘 다 `True` |
| 8 | **음수 불가** — `_invested_by_strategy` 가 0 미만으로 안 가고, 시도 시 **WARNING** | |
| 9 | **라이브 불변** — 페이퍼 경로 매수·매도 건수/금액 무변경 | |
| 10 | 🔑 **진입점 실호출** — 봇 초기화를 실제로 돌려 `provider` 와 `k_by_strategy` 가 **주입됐는지 단언** | 소스 문자열 단언은 죽은 경로도 통과한다 |

🔑 **10번이 필요한 이유**: 이 결함 자체가 *「생성자에 인자를 안 넘겨서」* 생겼다.
***같은 형태를 테스트로 막지 않으면 다음에 또 같은 자리에서 죽는다.***

**회귀 판정**: 전체 스위트를 **stash 후 베이스라인과 실패 «집합» 차분**으로 대조한다.
⚠️ repo 루트 + VS 번들 Python → [[reference-pytest-full-suite-invocation]]

---

## 9. 라이브 영향

| | |
|---|---|
| 페이퍼 매매 동작 | **0줄** — 두 가드 모두 섀도우가 기본이고, `can_add_position` 은 애초에 페이퍼 경로에 결선돼 있지 않다 |
| 실제 변화 | 로그 몇 줄 + EOD 리포트 **2줄**(자금상한 섀도우 · K한도 섀도우) |
| 발효 | 다음 **07:40 재기동** |
| 롤백 | `strategy_cap_enforce`·`position_k_enforce` 둘 다 기본 `False`. owner 전파는 되돌리면 원래대로 |

⚠️ **`can_add_position` 을 페이퍼 매수 경로에 결선하지 않는다** — 2026-07-29 사장님 결정이고
B안과 충돌한다. 이 스펙은 **실주문 경로의 판정 축만** 바꾼다.

---

## 10. 완료 판정

1. ✅ **§6 선행 측정 완료**(2026-08-13) — 원인은 「전략 셋이 이미 K 초과」였다.
   ⬜ 남은 것 = **런타임 `_position_entries` 대조**(owner=None 엔트리 존재 여부) → 구현 Task 1
2. 테스트 14개 통과 + 전체 스위트 실패 집합 **동일**
3. 재기동 후 로그에 **`provider 주입`·`k_by_strategy 주입`** 확인(진입점 실호출 테스트와 별개의 운영 확인)
4. EOD 리포트에 **`[전략상한 섀도우]`·`[K한도 섀도우]` 두 줄**이 **매일** 찍힘
   (N=0 이어도 줄은 나와야 한다 — ***줄이 없으면 「걸린 게 없다」가 아니라 「안 돌았다」다***)
5. 5거래일 후 **두 차단율을 각각** 산출 → 사전등록 기준(≤10%)으로 **가드별로 따로** 결선 판단
   ⚠️ 분모가 다르다(자금상한 = 매수 시도 / K한도 = **신규 종목** 매수 시도). 섞어 세지 말 것.
6. K 섀도우 기간에 **초과 전략 셋의 보유가 K 아래로 내려오는지** 기록
   (안 내려오면 결선이 아니라 **K 값 재검토**가 답이다)

---

## 11. 범위 밖

- 🔴 **휴장일 실주문 검증** — 별도 절차 문서. 이 스펙이 끝나야 검증 대상(가드 3종)이 확정된다.
  기존 항목: 수능일 15:20~16:30 일반주문 전멸 · `is_opening_protection()` 호출자 0건 ·
  `liquidation_handler.py:214` `or None`.
- 🔴 **`max_capital_pct` 설정값 자체의 적정성** — 섀도우 결과가 10% 를 넘으면 그때 별건으로.
- 🔴 **전략별 K 값 자체의 적정성** — §6 에서 `daytrading` 8/5 · `minervini` 6/3 처럼 **실제 운용이
  K 의 최대 2배**로 돌고 있음이 드러났다. K 가 틀렸는지 운용이 틀렸는지 이 스펙은 **판정하지 않는다.**
  ⚠️ ***근거 없이 K 를 실측치에 맞춰 올리면 「한도」가 아니라 「현상 추인」이 된다.*** 섀도우 5거래일
  결과를 보고 별건으로 판단한다.
- 🔴 **`liquidation_handler._force_complete_failed_stocks` 의 `is_virtual` 게이트 부재** —
  §0 의 blocker 주석이 지목한 곳이다. 이 스펙은 **owner 를 채워서** 문제를 없애지만,
  게이트 부재 자체는 손대지 않는다. 별건 백로그.

[[changelog-2026-08-11-max-capital-pct-dead-guard]] · [[changelog-2026-08-13-eod-monitoring]] ·
[[reference-pytest-full-suite-invocation]] · [[reusable-rules]]
