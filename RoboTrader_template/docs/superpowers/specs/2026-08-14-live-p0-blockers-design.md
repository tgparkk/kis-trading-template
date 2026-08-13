# 실매매 P0 blocker 4건 — 설계 (2026-08-14)

> **성격**: 실전 인스턴스(전략당 계좌 분리, C안) 투입의 전제 수정.
> **페이퍼 8전략 운영의 매매 동작 0줄.** 유일한 라이브 변화는 종료 경로 1건(§6-D4, 무해한 개선)이다.
> ⚠️ 이 스펙은 08-13 「실매매 가드 결선」 스펙(`116e16f`)과 **별건**이다 — 그쪽은 owner 결선,
> 이쪽은 그보다 앞선 「실전이 아예 성립하지 않는」 결함 4건이다.

---

## 0. 왜 지금

2026-08-14 실매매 전환 안정성 감사(메모리 `analysis-2026-08-14-live-transition-readiness`)에서
기존 백로그·스펙에 없던 **신규 blocker 4건**이 나왔고, 4건 전부 관리자가 원문으로 확증했다.

🔑 ***공통 뿌리: 호출부가 브로커 dict 에 없는 키를 기대했고, mock 이 그 기대를 발명해 테스트가
통과했다.*** 페이퍼는 `pending_orders` 를 만들지 않아 실주문 코드 904줄이 0줄 실행 — **페이퍼
안정성이 이 결함들을 원리적으로 노출할 수 없었다.**

| # | 결함 | 위치 (확증) | 실전 결과 |
|---|---|---|---|
| D1 | 총자금이 상수 1천만원 | `bot/initializer.py:678` 이 없는 키 `account_balance` 조회 (브로커 실제 키는 `total_balance` — `framework/broker.py:280-290`) | 모든 비율 가드가 실계좌 규모와 무관 |
| D2 | 재기동 복원 동작 불능 | `bot/state_restorer.py:787` 이 없는 키 `positions` 조회 → 실보유 항상 0건 | 복원 0 + 전 종목 「외부매도」 오탐, AUTO_RECONCILE 켜면 0원 매도 INSERT 장부 파괴 |
| D3 | EOD 실매도 실패 무음 | `bot/liquidation_handler.py:310`·`:422` 반환값 미검사 (페이퍼 브랜치 `:294`·`:408` 는 검사) | 매도 실패가 조용히 삼켜져 야간 무보호 |
| D4 | 크래시 복구 공백 | `KISBroker` 에 `get_pending_orders`·`shutdown` 미존재 (grep 0) — `state_restorer.py:829` hasattr 폴백 사문 · `initializer.py:708` AttributeError | 크래시 후 미체결 = 고아(매수)·중복매도(매도) · 종료 후반부 상시 실패 |

---

## 1. 결정 사항 (사장님 확정, 2026-08-14)

| # | 항목 | 결정 |
|---|---|---|
| 1 | 계좌 구조 | **C안** — 소수 전략만 `instances/`(전략당 계좌+프로세스)로 소액 실전. **페이퍼 8전략 운영은 병행 유지** |
| 2 | 착수 순서 | **이 P0 4건부터** (owner 스펙 116e16f 는 C안 채택으로 우선순위 하락) |
| 3 | 리허설 | 모의투자 경로 개발 없이 **소액 실탄 직행** ⇒ ***테스트가 유일한 방어선*** |
| 4 | 총자금 기준 | **`min(설정 상한, 실계좌 총평가금액)`** |
| 5 | 복원 가드 | 실계좌 조회실패·실계좌↔DB 불일치 = **기동 중단**(fail-closed) + 텔레그램. 자동 대사 제거 |
| 6 | 기동 시 미체결 | **전량 취소.** 취소 실패 = 기동 중단 |
| 7 | 수정 축 | **A안 — 호출부 수정** (브로커·KIS 파싱 계층 불변) + 실계약 contract test |

### 결정 7 의 근거 — KIS 공식 문서 대조 (2026-08-14)

잔고조회 API(TTTC8434R)는 한 호출에 요약(output2)과 보유종목(output1)을 같이 준다.
공식 필드 정의(koreainvestment/open-trading-api 공식 예제 `COLUMN_MAPPING`):
`tot_evlu_amt` **총평가금액** · `dnca_tot_amt` 예수금총금액 · `prvs_rcdl_excc_amt` 가수도정산금액(D+2 매수가능) ·
`nass_amt` 순자산금액 / output1: `pdno`·`hldg_qty` 보유수량·`pchs_avg_pric` 매입평균가격·`ord_psbl_qty`.

우리 하위 계층은 이걸 **정확히** 파싱한다(`api/kis_market_api.py:615-624`·`:661-671` — `total_value`=총평가,
`available_amount`=D+2, `stocks`=보유목록). `KISBroker.get_holdings()`(`framework/broker.py:296-326`)도
output1 을 그대로 준다(`get_existing_holdings` = `get_account_balance()['stocks']`, `kis_market_api.py:746-759`).
🔑 ***KIS 가 안 주는 게 아니라 중간 계층이 이름을 두 번 번역하다 흘렸다*** — 같은 값이
`tot_evlu_amt`(KIS) → `total_value`(api) → `total_balance`(broker) 로 바뀌는데 호출부는 제3의 이름
`account_balance`/`positions` 를 기대했다. ⇒ 틀린 기대를 품은 호출부 두 곳만 고친다.

---

## 2. 설계

### D1. 총자금 결선 (`bot/initializer.py:673-685`)

```python
# 실전 분기 (else, :673-685) 교체
balance = broker.get_account_balance()          # dict, 실패 시 {} (broker.py:278·294)
total_eval = float(balance.get('total_balance', 0)) if balance else 0
cap = config의 real_total_funds_cap             # 신설 키, 원 단위
if total_eval <= 0: 기동 중단                    # 조회 실패·빈 계좌 동일 취급
if cap is None or cap <= 0: 기동 중단            # 실전 모드에서 상한은 필수
total_funds = min(cap, total_eval)
```

- 신설 설정 키: **`real_total_funds_cap`** (인스턴스별 `trading_config.json`, 원 단위).
  페이퍼 모드에서는 읽지 않는다.
- 현행 「조용히 1천만원」 폴백(`:678` 기본값 · `:684-685` 실패 분기) **전부 제거** — 실전에서
  총자금의 무언 기본값은 존재하지 않는다.
- 🔑 ***min() 인 이유***: 계좌에 실수로 큰돈이 들어 있어도 상한까지만 운용(소액 시작 의도),
  상한을 계좌보다 크게 적어도 실계좌 이상으로 안 잡음(과대주문 후 KIS 거부 방지). 양방향 안전.
- `sync_with_account` 주기 결선(장중 재동기화)·T+2 매수가능금액 게이트는 **범위 밖**(§7).

### D2. 실전 재기동 복원 결선 (`bot/state_restorer.py`)

**(a) 보유 조회 교체** — `:780-789` 를 `self.broker.get_holdings()` 로 교체.
반환 항목 키(`stock_code`/`quantity`/`avg_price`, `kis_market_api.py:711-720`)는 복원 루프(`:849-`)가
기대하는 형태와 일치한다. 실패 → **기동 중단**(현행 「DB 폴백으로 계속」 `:782-785` 제거).

⚠️ **「빈 계좌」와 「조회 실패」의 판별** — `get_holdings()` 는 실패 시 예외가 아니라 **빈 리스트를
반환한다**(`broker.py:313`·`:319-320`·`:326` — 오류 삼킴). 빈 리스트만으로는 둘을 구분할 수 없다.
브로커는 불변(결정 7, 소비자 `broker.py:442 get_sellable_quantity` 존재)이므로 **요약 교차검증**으로 닫는다:
D1 에서 이미 받은 `get_account_balance()['total_stocks']` 가 **N>0 인데 `get_holdings()` 가 0건이면
조회 실패로 간주 → 기동 중단**. 둘 다 0 이면 진짜 빈 계좌 = 정상 기동.
🔑 ***단독 단언은 판별력이 없다 — 두 소스의 대칭 확인이 「0건」을 데이터로 만든다***(기존 재사용 규칙).

**(b) fail-closed 대사** — `_detect_holdings_mismatch`(`:977-1037`)는 감지·분류(현행 유지)하되,
불일치가 1건이라도 있으면 **기동 중단** + 텔레그램에 불일치 목록(유형·종목·수량).
`_reconcile_mismatches`(`:1039-1150`)와 `STATE_RESTORATION_AUTO_RECONCILE`(`config/constants.py:168`)는
**코드째 제거** — 0원 매도 INSERT 라는 장부 파괴 경로를 남겨두지 않는다.

**(c) 오탐 원인 동시 교정** — DB 미청산을 `db_holdings_dict[code]=...` 로 덮어쓰던 것(`:811-819`)을
**종목별 합산**(수량 SUM · 매입가 가중평균)으로. 분할매수 2행이면 현행은 수량이 작게 잡혀
`qty_diff` 오탐 → 기동 중단 정책에서는 오탐 = 기동 불능이므로 이 교정은 (b) 의 전제다.

**(d) 기동 중단 메커니즘** — 전용 예외 `LiveStartupAbort(사유, 상세)` 를 신설하고
initializer/state_restorer 가 raise, `main.py` 기동 절차가 잡아 **텔레그램 경보 → 프로세스 종료**.
🔑 ***조용히 계속하는 경로를 하나도 남기지 않는다*** — 이 프로젝트의 반복 실패 형태가
「데이터 부족이 정상 라벨로 나온다」였다.

### D3. EOD 실매도 반환값 검사 (`bot/liquidation_handler.py`)

`:310`(본청산)·`:422`(재시도) 의 `execute_sell_order(...)` 반환 bool 을 검사, `False`/예외 시
`failed_stocks` 에 `(code, owner)` 적재 — **페이퍼 브랜치(`:294`·`:408`)와 대칭**.
이후는 기존 체인(재시도 3회 → `_force_complete_failed_stocks` → CRITICAL 텔레그램) 그대로.

⚠️ 강제완료가 실전에선 「장부만 청산, 실물 잔존」인 잔여 위험은 이 스펙이 없애지 않는다.

🔴 **정정(2026-08-14 최종 리뷰 I3)**: 위 초안은 「다음날 기동 시 D2(b) 가 실계좌↔DB
불일치로 잡아 기동을 중단시키므로 사장님 확인이 구조적으로 강제된다」고 적었으나 이는
틀렸다 — **강제완료(`_force_complete_failed_stocks`)는 DB 부작용이 0**이다(장부에 매도를
기록하지 않고 메모리 상태와 자금만 정리한다). 그래서 실물은 실계좌에 잔존하는데 DB 는
애초에 그 종목을 청산으로 기록한 적이 없어 **수량이 그대로 일치**하고, D2(b) 의 계좌-DB
대사는 수량이 어긋나는 경우(예: 부분체결)만 잡으므로 이 케이스를 **잡지 못한다**. D3 의
실패 격리와 D2 의 fail-closed 는 한 사슬이 아니다.

**잔여 위험의 실제 통지 경로는 강제완료 시점의 EOD CRITICAL 텔레그램뿐**이다
(`bot/liquidation_handler.py` `_force_complete_failed_stocks` → CRITICAL 알림, `:539-557`).
강제완료 시 DB 에 마커(예: 「수동 확인 필요」 플래그)를 남겨 다음날 대사가 이를 잡게 하는
것은 이 스펙의 범위 밖이며 **백로그**로 남긴다.

### D4. 크래시 복구 (`framework/broker.py` + `bot/state_restorer.py` + `bot/initializer.py`)

**(a) `KISBroker.get_pending_orders()` 신설** — 기존 미체결조회 래퍼
`get_inquire_psbl_rvsecncl_lst()`(`api/kis_order_api.py:168`, TTTC8036R)를 감싸 미체결 목록을
dict 리스트로 반환(주문번호·종목·매수/매도 구분·잔량). 이 API 는 이미 `cancel_order`(`broker.py:685`)가
쓰고 있어 응답 스키마가 검증돼 있다.

**(b) 기동 시 전량 취소 단계 신설** — 실전 복원 절차 **첫 단계**(잔고 조회 «전»):
```
미체결 조회 → N건이면 전량 cancel_order → 재조회로 0건 확인 → 잔고 조회 → 복원
```
순서 근거: 취소가 먼저여야 부분체결분이 잔고에 확정 반영된 뒤 복원된다.
취소 실패·재조회에서 잔존 확인·조회 자체 실패 → **기동 중단**(D2(d) 와 동일 메커니즘).

**(c) 죽은 폴백 정리** — 「전량 취소」 정책으로 SELL_PENDING 복원(`state_restorer.py:826-841`,
hasattr 폴백으로 이미 사문)은 불필요 → 제거. 복원은 항상 미체결 0 상태에서 시작한다.

**(d) `broker.shutdown()` 교정** — `initializer.py:708` 을 `await broker.disconnect()` 로.
⚠️ **페이퍼에도 영향** — 지금까지 매번 AttributeError → `:717` except 로 빠져 PID 삭제(`:711-713`)·
「시스템 종료 완료」가 상시 스킵되던 것이 정상화된다(레포 루트 `robotrader.pid` 잔존과 정합).
무해한 개선이나 **라이브 변화로 명시**하고 발효는 다음 페이퍼 재기동.

---

## 3. 데이터 흐름 (수정 후, 실전 기동)

```
main → initializer.initialize_system
  ├─ D1  총자금 = min(real_total_funds_cap, broker.get_account_balance()['total_balance'])
  │       (조회실패·0원·상한미설정 → LiveStartupAbort)  · _initialize_fund_manager(:586)
  ├─ D4(b) 미체결 전량 취소 — 복원(:596)의 첫 단계, 잔고 조회 «전» (실패 → LiveStartupAbort)
  ├─ D2  보유 = broker.get_holdings()  (total_stocks>0 인데 0건 = 조회실패 → LiveStartupAbort)
  │       ├─ DB 미청산 합산 대조 → 불일치 ≥1 → LiveStartupAbort(목록 첨부)
  │       └─ 일치 → 실계좌 값(수량·평단)으로 복원 (기존 로직)
  └─ 이후 기존 기동 계속
LiveStartupAbort → 텔레그램 경보 → 프로세스 종료 (조용한 계속 없음)
```

---

## 4. 테스트 (전부 red 먼저 — 결정 3 에 의해 유일한 방어선)

| # | 무엇 | red 조건 |
|---|---|---|
| 1 | 🔴 **D1 재현** — 실브로커 반환 키로 총자금 산출 시 `total_balance` 를 읽는다 | 수정 전: 상수 1천만원 |
| 2 | D1 fail-closed — 조회 실패({})·0원·상한 미설정 각각 `LiveStartupAbort` | 수정 전: 조용히 1천만원 |
| 3 | D1 min — 상한<실계좌·상한>실계좌 양방향에서 작은 값 채택 | |
| 4 | 🔴 **D2 재현** — 실브로커 계약(`get_holdings` 리스트)으로 복원 N건 성립 | 수정 전: 0건 |
| 5 | D2 불일치 → `LiveStartupAbort` + 0원 매도 INSERT 가 **어떤 경로로도 불가**(함수 부재) | 수정 전: AUTO_RECONCILE 로 INSERT |
| 6 | D2 합산 — 같은 종목 BUY 2행(분할매수)이 수량 SUM·가중평균으로 대조돼 오탐 0 | 수정 전: qty_diff 오탐 |
| 7 | D2 빈 계좌 — `total_stocks=0` & holdings 0건 & DB 0 = 정상 기동 | |
| 7b | 🔑 D2 판별 — `total_stocks>0` 인데 holdings 0건 = 조회 실패로 `LiveStartupAbort` (빈 리스트 오류 삼킴 대응) | 수정 전: 구분 불가 |
| 8 | 🔴 **D3 재현** — 실매도 반환 False 가 `failed_stocks` 에 적재돼 재시도 체인 발동 | 수정 전: 무음 |
| 9 | D4 — `get_pending_orders` 가 TTTC8036R 응답을 dict 리스트로 변환 | |
| 10 | D4 — 기동 취소: N건 취소 성공 후 진행 / 취소 실패·잔존 시 `LiveStartupAbort` | |
| 11 | D4 — `shutdown` 경로가 `disconnect()` 를 호출하고 PID 삭제까지 도달 | 수정 전: AttributeError |
| 12 | 🔑 **실계약 contract test** — `KISBroker.get_account_balance()` 반환 키 집합·`get_holdings()` 항목 키 집합을 고정. **테스트 mock 은 이 계약에서 파생되는 공용 fixture 만 사용** | |
| 13 | 🔴 은폐범 교정 — `tests/test_state_restorer_live_real_table.py:130-136` 의 발명된 mock(`positions` 키·`get_pending_orders` 존재 가정)을 실계약 fixture 로 교체 | 현행 green 이 결함 은폐 중 |
| 14 | 🔑 **진입점 실호출** — 실전 기동 절차를 실제로 돌려 호출 «순서»(취소→총자금→잔고→복원) 단언. 소스 문자열 단언 금지 | |
| 15 | **라이브 불변** — 페이퍼 경로 매수·매도 건수/금액 무변경 (D4(d) 종료 경로만 예외로 명시) | |

**회귀 판정**: 전체 스위트를 **stash 후 베이스라인과 실패 집합 차분**. repo 루트 + VS 번들 Python
([[reference-pytest-full-suite-invocation]]). 🔴 **라이브 트리에서 테스트 금지 — 워크트리 작업.**

🔑 **12·13 이 이 스펙의 심장이다.** 이번 결함 4건 전부 「mock 이 계약을 발명」해 숨었다.
같은 형태를 테스트로 막지 않으면 다음에 또 같은 자리에서 죽는다.

---

## 5. 라이브 영향

| | |
|---|---|
| 페이퍼 매매 동작 | **0줄** — D1·D2·D3 은 실전 분기, D4(a-c) 는 실전 전용 신설 |
| 페이퍼 변화 1건 | D4(d) 종료 경로 정상화 (PID 삭제·disconnect 가 처음으로 실행됨) — 발효는 다음 재기동 |
| 실전 인스턴스 | 이 스펙 완료 + 별건(인스턴스 셋업·전략 선정) 후 첫 기동 |
| 롤백 | 각 수정은 독립 커밋. D4(d) 만 페이퍼 관측 대상 |

---

## 6. 완료 판정

1. 테스트 16개 통과 + 전체 스위트 실패 집합 베이스라인과 **동일**
2. 페이퍼 재기동 후 종료 로그에 「PID 파일 삭제 완료」·「시스템 종료 완료」 확인 (D4(d) 발효 확인)
3. `STATE_RESTORATION_AUTO_RECONCILE`·`_reconcile_mismatches` 가 코드베이스에서 **소멸** (grep 0)
4. 실전 첫 기동 리허설(소액 계좌, 별건 절차)에서 `LiveStartupAbort` 경보 체인이 실제로 텔레그램에 도달하는지 확인 — **줄이 없으면 「걸린 게 없다」가 아니라 「안 돌았다」다**

---

## 7. 범위 밖 (별건 후속)

- **owner 결선**(스펙 `116e16f`) — C안 채택으로 우선순위 하락, 한 계좌 다전략 재개 시 필수
- **주문/시세 API 예산·우선순위 레인 분리** — 감사 P0, 이 스펙과 독립
- **T+2 매수가능금액 게이트**(`get_inquire_psbl_order` 매수 직전 결선) · `sync_with_account` 주기 결선
- **손절 스킵 debug→WARNING 승격**(`position_monitor.py:206-212`) · `last_price` TTL
- **실전 tp/sl 영속화**(`real_trading_records` 스키마 변경 + `_real_buy_record_id` 대입 경로)
- **일일 손실 카운터 재기동 리셋** — 실전에서 리스크 한도 우회가 되므로 실전 투입 전 별건 검토
- **시장 CB 프로듀서 부재** · VI arm 1회성 — 「가드가 있다」는 전제가 현재 거짓임을 문서화만
- **실전 인스턴스 셋업 절차·투입 전략 선정** — 계좌 개설·앱키·`real_total_funds_cap` 값 포함

[[analysis-2026-08-14-live-transition-readiness]] · `docs/superpowers/specs/2026-08-13-live-trading-guards-design.md` · [[reusable-rules]]
