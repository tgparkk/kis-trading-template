# 전략 소유권 모델 (Ownership Model)

> 다전략 운영에서 "이 포지션·주문은 누구 것인가"를 판정하는 규칙. 관련 코드가
> `core/`·`bot/`·`db/` 전반에 흩어져 있어 별도 문서로 뺀다.
> 라우터: [../CLAUDE.md](../CLAUDE.md) · 모듈 개요: [code/MODULES.md](code/MODULES.md)

---

## 1. 전략 신원 모델 — 세 개의 상호 교환 불가 키

전략 하나를 가리키는 표기가 세 가지이고, 서로 바꿔 쓸 수 없다:

| 키 | 예 (`rs_leader`) | 용도 |
|---|---|---|
| **폴더키** | `rs_leader` | 정본 dict 키. `strategies_by_key`(`core/trading_decision_engine.py:62,90`) · 복원 1차 조회(`bot/state_restorer.py:98-122` `_resolve_owner_strategy`) · 다중전략 모드 후보 등록(`bot/candidate_loader.py::_load_candidates_multi_strategy` `:235-240` — `state_restorer.py::_owner_group_key` docstring `:805-807` 근거) · **단일전략 모드 후보 등록도 09-16 부터 폴더키**(`a758fac`, 아래 후기) |
| **클래스명(표기명)** | `RSLeaderStrategy` (`strategy.name`, `strategies/rs_leader/strategy.py:24`) | 로그·DB 표기용 display name. ~~단일전략 모드 후보 등록(`candidate_loader.py:100`)~~ → `a758fac` 이후 strategies dict 가 0개(레거시/전략 미로딩)일 때의 폴백 표기(`candidate_loader.py:128`)로만 남음 — 2개 이상은 `:71-73` 에서 다중전략 분기로 빠져 여기 오지 않는다 |
| **`None`/빈 문자열** | — | 무소유(unowned) |

### 🔴 `core/trading_context.py:536`가 폴더키를 클래스명으로 덮어쓴다

매수 성공 직후:
```python
# trading_context.py:535-537
if self._current_strategy_name:
    trading_stock.owner_strategy_name = self._current_strategy_name  # 클래스명
    trading_stock.owner_strategy = self._strategies_dict.get(self._strategy_key)
```
그런데 같은 클래스의 생성자 주석(`trading_context.py:64-67`)은 정반대로 못박는다:

> `_strategy_key`: `_strategies_dict` 조회용 키(폴더명) — dict lookup에는 항상 이 값을 사용.
> `_current_strategy_name`: 표기명 — ... **dict 키로는 절대 사용 금지.**

2026-08-14 커밋 `44a91e4`가 정확히 이 위반을 고쳤다: `_resolve_owner_strategy`가 폴더키 전용 맵(`strategies_by_key`)만 조회해 `:536`가 남긴 클래스명 표기가 **항상 miss**하고, 조용히 첫 전략(config 순서 1번)으로 폴백하고 있었다.

**코드베이스의 alias-tolerant 조회는 전부 이 한 줄을 보완하기 위해 존재한다.** `:536`을 폴더키로 정규화하면 아래 네 곳을 전부 지울 수 있지만, 실거래 owner 문자열이 전역으로 바뀌는 변경이라 **별도 스코프로 다뤄야 한다**:

- `TradingContext._get_own_trading_stock` — `core/trading_context.py:88-109` (폴더키 → 클래스명 순회, 둘 다 실패 시 종목코드 단독 폴백)
- `StateRestorer._resolve_owner_strategy` — `bot/state_restorer.py:98-122`
- `OrderCompletionHandler._find_owned_stock` — `core/trading/order_completion_handler.py:92`~ (`_owner_aliases` `:70` 로 별칭 순회 `:108`, 다중소유 모호 시 `None` 반환 `:122`)
- `StateRestorer._owner_group_key` — `bot/state_restorer.py:802-825` (두 표기를 같은 전략 인스턴스로 접어 「2 owner」 오판을 막음)

### 지켜야 할 규칙

- **클래스명을 dict 키로 쓰지 말 것** (`trading_context.py:64-67` — 2026-08-14에 고친 결함이 정확히 이 위반이었다).
- owner를 판정하는 조회는 **반드시 2단**(폴더키 → 클래스명)이어야 한다.
- 조회 실패는 **로그로 남기고**, 기본 전략(첫 번째 전략)으로 조용히 폴백하지 말 것.

---

## 2. 실주문 경로의 소유권 게이트 (2026-08-14 신규)

- **주문 시점**: owner가 해석되지 않는 **실매수는 주문 전에 거부**된다.
  - 게이트: `core/orders/order_executor.py:102-115`
  - 판정: `_owner_resolves`(`order_executor.py:46-66`) — 라벨이 빈 값이거나 페이퍼 모드면 무조건 통과(`:54-58`), 판정 자체가 실패하면 차단이 아니라 통과(`:65-66`, "판정 불가를 «차단» 으로 바꾸지 않는다").
- **매도는 의도적으로 게이트를 걸지 않는다.** `order_executor.py:108-109` 주석:
  > 매도에는 걸지 않는다 — 소유 전략을 모른다고 청산을 막으면 포지션이 갇힌다. 게이트는 «새 위험을 만드는» 쪽에만 건다.
- **복원 시점**: `StateRestorer._classify_orphan_legs`(`bot/state_restorer.py:1009-1085`)가 레그를 분류한다.
  - 해석도 설명도 안 되는 라벨(오타·삭제된 전략명) → **기동 중단(abort)**
  - 설명 가능한 두 부류 → **격리 + ERROR 로그**(`:1078-1082`, 전략 고유 청산 없이 `position_monitor`의 tp/sl·EOD 일괄청산 백스톱만 적용):
    1. config에 선언됐으나 미로드(`enabled:false` 또는 `on_init` 실패)
    2. 라벨이 `unknown`/공백 (`_UNNAMED_LABELS = frozenset({"", "unknown"})`, `state_restorer.py:984`)
  - 메시지가 고칠 대상을 명시한다 — config 항목인지 실거래 테이블 `strategy` 컬럼 `UPDATE`인지(`state_restorer.py:1061-1077`).
- 정책은 2026-08-14 하루에 두 번 바뀌었다: fail-open(ERROR만) → fail-closed(전량 중단) → **현재: 주문 시점 하드스톱 + 복원 시점 선별 격리**. 각 단계를 뒤집은 이유가 `_classify_orphan_legs` docstring(`state_restorer.py:1009-1043`)에 남아 있다. **재론의 전에 반드시 그 docstring을 읽을 것.**

### `unknown`은 손상이 아니라 앱이 정상적으로 쓰는 값이다

`db/repositories/trading.py:58-76` `_sanitize_strategy`가 `strategy` 컬럼에 매매 사유 키워드(`_REASON_KEYWORDS`, `:20` = 매도·매수·수익률·손절·익절·청산·복원·복구·조건·점수)가 섞인 값을 `"unknown"`으로 치환한다. 그 외 네 경로도 직접 `"unknown"`을 쓴다:

- `core/orders/order_db_handler.py:75-115` `_get_strategy_name_for_order` — 최후 폴백 `:115`
- `core/trading/order_completion_handler.py:544-559` `_get_strategy_name` — 최후 폴백 `:559`
- `bot/position_sync.py:110-115`
- `bot/candidate_loader.py:128` (단일전략 분기에서 strategies dict 가 0개일 때의 `"unknown"` 폴백 — `a758fac` 이후 dict 가 1개면 폴더키를 쓰므로 여기엔 안 온다)

⇒ `unknown` 라벨을 보고 "데이터 손상"으로 취급하지 말 것.

---

## 3. 미청산 판정은 수량 인식이어야 한다

- 실거래 경로의 미청산·짝짓기 쿼리는 `HAVING b.quantity - COALESCE(SUM(s.quantity), 0) > 0`로 **잔량**을 돌려준다:
  - `get_real_open_positions` — `db/repositories/trading.py:475`~(HAVING `:508`). 존재성 술어(`NOT EXISTS ... action='SELL'`)를 쓰면 10주 중 6주만 팔아도 BUY 행 전체가 닫혀 "브로커 4주 vs DB 0주"가 되고 계좌-DB 대사가 아침 기동을 막는다(주석 `:488-496`).
  - `get_last_open_real_buy` — `db/repositories/trading.py:190-245`(HAVING `:220`). 부분매도된 행도 다음 매도가 붙을 자리이므로 짝짓기 조회도 수량 인식이어야 한다(주석 `:211-212`).
- **가상(페이퍼) 경로는 의도적으로 그대로 둔다.** `get_virtual_open_positions` — `db/repositories/trading.py:431`~(`NOT EXISTS` `:451-454`). 주석(`:434-439`): 페이퍼 체결은 원자적이라 `SELL.quantity ≠ BUY.quantity`인 행이 0이라서 결함이 발화하지 않고, 매일 도는 경로를 이득 0으로 바꾸면 회귀 위험만 커진다.
- 이 비대칭은 `tests/test_live_sell_buy_record_pairing.py::test_virtual_open_positions_is_deliberately_untouched`(`:363-375`)가 고정한다 — 가상 쿼리에 `NOT EXISTS`가 있어야 통과하는 테스트다. **한쪽만 "고치면" 이 테스트가 깨진다 — 왜 그대로 뒀는지 먼저 읽을 것.**

---

## 후기 (2026-09-17) — 단일전략 모드 후보 등록도 이제 폴더키다

- **`a758fac`(2026-09-15 · `2c045de` 머지 · 발효 2026-09-16 07:40)** 로 `bot/candidate_loader.py::_load_screener_candidates` 의 **단일전략 분기**가 바뀌었다: `self._bot.strategies` dict 가 정확히 1개면 그 **폴더키**(`next(iter(strategies))`, `:124-126`)를 owner 로 등록한다. 클래스명(`self.strategy.name`)·`"unknown"` 폴백은 dict 가 0개(레거시/전략 미로딩)일 때만 남고(2개 이상은 `:71-73` 에서 다중전략 분기로 빠져 여기 오지 않는다), 그때는 `[소유자미해결]` WARNING 을 찍는다(`:127-138`).
- 이유(P1-2): `TradingContext` 는 폴더키(`_strategy_key`)로 후보를 조회하므로 클래스명으로 등록된 후보는 단일 전략 봇(실전 인스턴스)에서 «안 보여» 종일 무거래가 됐다. 회귀 고정 → `tests/test_live_min_fix_set_20260915.py`.
- 다중전략 분기(`_load_candidates_multi_strategy`, `:235-240`)는 원래부터 폴더키였다. ⇒ §1 표의 「클래스명 = 단일전략 모드 후보 등록」은 **09-16 이후 더 이상 참이 아니다**(표에 취소선). `bot/state_restorer.py::_owner_group_key` docstring(`:805-807`)의 「`:100` 은 클래스명」 서술은 코드 주석이라 이 문서에서 고치지 않는다(주석 갱신 = 코드 변경).
- `core/trading_context.py:536`(매수 성공 직후 `owner_strategy_name = 클래스명`)은 **그대로다** — §1 의 alias-tolerant 조회 4곳도 그대로 필요하다.
- 이 문서의 줄번호는 2026-09-17 에 재확인했다(위 본문에 반영). 이후 드리프트하면 함수명을 기준으로 찾을 것.
