# 매매 파이프라인 전 과정 고수 개발자 검토 (2026-09-14 밤 · 읽기 전용 · rev.1)

> **사장님 지시 원문** — "고수개발자 소환해서 매수후보, 데이터수집, 매수진입, 매도진입, 주문체결, 프로그램 종료 후 DB 읽어서 보유종목 메모리 로딩 등 모든 과정에 대해 검토."
>
> **성격** — 이 문서는 **설계 검토 보고서**다. **코드 0줄 수정**, pytest 0회, git 편집 0건. 아래 「수정안」은 전부 **제안**이며 승인·실행이 아니다. **페이퍼 8전략 봇은 이 검토로 아무것도 바뀌지 않았다.** DB 는 SELECT 만, 로그는 읽기만 했다.
>
> **방법** — 6단계를 architect 3명이 나눠 ①실제 함수 사슬 추적(파일:줄 체인) ②설계 판정(상태머신·멱등성·경쟁조건·복구·관측가능성·SSOT) ③09-14(월) 로그·DB 실측 대조 → **critic 이 3편 전수 적대 검증**(신규 32건 판정 + 모순 3건 재조정) → **관리자가 DB 제약·코드 원문 직접 확인**. 운영 코드(`core/ bot/ framework/ api/ strategies/ config/ db/ utils/ runners/ collectors/ main.py`)만 근거로 썼고 연구 코드(`scripts/ multiverse/ backtest/ archive/ lib/ books/ council/`)는 근거에서 제외했다.
>
> **자매 문서** — `docs/audit_2026-09-14_real_trading_switch.md` (실전 전환 사전 감사 · 결함 40건 · P1 10건).
> **이 문서는 그 위에 얹는 «설계 검토»다.** 같은 결함을 다시 세지 않고, 중복은 **번호만 참조**한다(P1-2, P2-19 처럼).
>
> **산출물 폴더** — `RoboTrader_template/scratchpad/real_trading_audit_20260914/`
> (`BRIEF2_pipeline_review.md` · `review_A_candidates_data.md` · `review_B_entry_exit.md` · `review_C_fill_restore.md` · `CRITIC_verify2.md`)
>
> **검토 3편과 검수가 다르면 검수가 이긴다.** 이 문서의 척추는 `CRITIC_verify2.md` 다.

### 검수가 철회·정정한 것 (5줄 요약 · 상세는 §3)

1. ~~B-10 「실전 첫날 15:00 에 의도치 않은 시장가 전량 청산」~~ → **REFUTED · P3 강등**. 폴백이 `owner or decision_engine.strategy` 라 1전략 실전에서는 두 번째가 채워지고, 채워져도 swing 이라 스킵되며, 애초에 그 포지션은 실전 표에 없다(관리자 원문 확인).
2. ~~「한 전략 on_tick 이 72초마다」~~ → **약 290초(4.8분)**. B 자신의 실측 80회가 자기 주장을 반증한다(320회여야 함).
3. ~~「09:00 에 이벤트 루프가 약 60초 멈춘다」~~ → **확정 구간은 34초**(09:00:28~09:01:02). 그 앞 28초는 로그가 비어 판정 불가.
4. ~~A 의 「지금 당장 = `to_thread` 로 내린다」~~ → **권고 철회**. 후보 로드가 메인 루프 1~5단계보다 **앞에서 순차 await** 되므로 스레드로 내려도 감시 공백은 그대로다. 유효한 처방은 **08:5x 장전 스냅샷 분리** 하나뿐.
5. ~~기존 P2-19 「미체결 타임아웃 → 5분마다 재발주, 종목당 최대 약 75회/일」~~ → **REFUTED**. 재발주 코드 자체가 없고(`grep place_buy_order` 전수 2건, 하나는 주석 처리), 실제 사고는 정반대인 **「조용한 증발」**(B-4 · X9)이다.
   (그 밖에 A-N4·A-N2·A-N9·C-N5 일부가 하향, 검수자 신규 2건 CR-1·CR-2 추가.)

---

## 0. 고수의 한 줄 판정

| 단계 | 한 줄 판정 |
|---|---|
| **① 매수후보 선정** | 「없다」와 「고장」을 값으로 가른 것은 이 코드베이스 최고 수준인데, **정작 상한값이 비활성 `sample` 전략 파라미터에서 온다** — 매일 스냅샷의 아래쪽 절반이 조용히 버려진다. |
| **② 데이터 수집** | **폴링의 절반 이상이 소비자가 0**이고, 실제로 소비되는 「분봉」은 `O=H=L=C·volume=0` 인 가짜 봉이다. 3초라 불리는 주기는 실측 **12.2초**다. |
| **③ 매수 진입** | 가드가 14겹인데 09-14 에 **13겹이 한 번도 발화하지 않았고**, 「한 번만 산다」를 지키는 실효 방벽은 **상태 인덱스 하나**다. 그리고 그 상태 머신은 **강제되지 않는다**(경고만 하고 전이한다). |
| **④ 매도 진입** | 한 포지션에 **판단 주체가 최대 4개**인데 조정자가 없다. 09-14 손절 **7/7 이 전략이 아니라 프레임워크 백스톱**이었고, 고도화 3전략의 매도는 **0건**이다. |
| **⑤ 주문 체결** | 「설계가 나쁜 코드」가 아니라 **「한 번도 켜 본 적 없는 코드」**다. 페이퍼는 `OrderManager` 를 통째로 우회하므로 상태머신·타임아웃·부분체결·오탐복구는 **실전 첫날이 첫 가동**이다. |
| **⑥ 재기동 복원** | 매일 도는 잘 다듬어진 코드지만 **진실원이 세 겹인데 교차검증이 0줄**이고, 재기동은 **「포지션은 유지하고 브레이크만 전부 푼다」**. |
| **전체** | **판단 계층은 매일 검증되고 있고 대체로 견고하다. 실행·자금·원장 계층은 페이퍼에서 한 번도 돌지 않았고, 그 계층에만 P1 이 몰려 있다.** 지금 가장 시급한 것은 매매 룰이 아니라 **계기(로그)와 원장 제약**이다 — 3전략 고도화의 관측 분모가 이미 오염돼 있기 때문이다. |

---

## 1. 쉽게 읽는 요약 — 예시로 (사장님용)

> 숫자는 **검수가 확정한 값만** 썼다. (추정)이라 적힌 것은 확정되지 않은 값이다.

**① 「후보를 20개 만들어 놓고 10개만 쓴다」**
매일 아침 봇이 전략별로 후보를 **20개씩** 만들어 DB(`screener_snapshots`)에 넣는다. 그런데 정작 쓸 때는 **10개만** 가져온다. 왜 10인가 — `config/trading_config.json:26` 의 **비활성 예제 전략 `sample` 의 파라미터**가 그 값이기 때문이다. 09-14 로그가 그대로 자백한다: `스냅샷 20건, 목표 10건`. 106행을 만들어 **56종목만 썼다**.

**② 「09:00:28~09:01:02 사이 34초 동안 봇이 통째로 멈춘다 — 그 34초엔 손절도 안 본다」**
후보를 만드는 작업(전 종목 스캔)이 비동기 함수 안에서 **동기로** 돈다. 그동안 시세 수집·미체결 확인·**손절 감시가 한 번도 안 돈다**. 09-14 는 보유 36종목에 KOSPI −3.26% 인 날이었다. 실탄으로 바꾸면 이 34초가 그대로 돈이다.
(⚠️ 그 앞 09:00:00~09:00:28 구간은 로그가 비어 있어 **멈춘 건지 그냥 30초 폴링 간격인지 판정 불가**다. 확정된 것은 34초뿐이다.)

**③ 「'3초마다 시세 확인'은 실제로 12초다」**
설정은 3초인데 실측은 **12.2초**다. 모든 KIS 호출이 0.1초 간격으로 한 줄로 서기 때문이다(전역 락). 한 라운드에 약 111~114번 호출하니 11~12초가 걸리고, `sleep(3 − 경과)` 는 **항상 0**이 된다. 후보를 늘리면 이 숫자가 **선형으로 나빠진다** — 그리고 그 호출의 절반 이상은 **아무도 읽지 않는 값**이다.

**④ 「한 전략의 차례는 72초가 아니라 약 5분에 한 번 온다」**
설정상으로는 9초마다 한 전략씩 돌아 8전략이면 72초 주기여야 한다. 그런데 한 라운드가 12.2초이므로 실제는 **12.2 × 3 × 8 = 약 290초**다. 실측이 이를 뒷받침한다 — 하루 종일 돌았는데 전략당 `on_tick` 이 **79~80회**뿐이다(72초 주기면 320회여야 한다). ⇒ **전략 룰이 판단할 기회 자체가 예상의 1/4**이고, 그만큼 프레임워크 백스톱 의존도가 높다.

**⑤ 「ma20·minervini 는 9/14 개장 첫 틱부터 살 수 없었는데, 로그는 '조건 미충족'과 똑같이 찍힌다」**
두 전략은 아침 07:40 복원 시점에 이미 보유 한도(`max_positions` 5 / 3)를 **꽉 채운 상태**였다. 그래서 하루 종일 후보를 평가조차 하지 않고 즉시 `None` 을 돌려줬다. 문제는 그 `None` 이 「룰이 안 맞았다」와 **로그가 글자 하나 다르지 않다**는 것이다(`[신호없음] … generate_signal None 반환`). ⇒ 「ma20 이 폭락일에 0건 매수 = 룰이 안 걸렸다」로 읽으면 **정반대 결론**이 나온다. 실제로는 **룰을 평가조차 안 했다.** 3전략 고도화의 관측이 전부 이 로그를 분모로 쓴다.

**⑥ 「손절 7건 전부 전략이 아니라 프레임워크 백스톱이 팔았고, 3건이 09:05:10~12 세 초 안에 몰렸다」**
09-14 매도 9건 중 **손절 7건 전부**가 전략 룰이 아니라 공통 백스톱(`position_monitor`)이 판 것이다. 고도화 3전략의 매도는 **0건**. 그리고 09:00~09:05 에 손절을 막는 유예 창이 있는데, 09:05:00 에 그게 풀리자 **3초 만에 3건**(전체의 43%)이 쏟아졌다. 유예는 갭을 **막은 게 아니라 늦춘 것**이다.

**⑦ 「주문 관리자는 페이퍼에서 한 번도 안 돌았다 — 실전 첫날이 첫 가동」**
페이퍼 매매는 `OrderManager` 를 **통째로 우회**한다. 09-14 로그 실측: `매수 주문 시도` 0 · `주문 완전 체결` 0 · `체결 콜백 수신` 0 · `미체결 주문: 0건` ×20. ⇒ **「5개월 무사고」는 판단 계층에 대해서만 증거**이고, 주문·체결·타임아웃·부분체결·자금 확정 계층에 대해서는 **증거가 0회**다.

**⑧ 「매수 부분체결 취소가 실패하면 자금 장부가 두 번 깨진다」** (실전 P1 · 가장 위험)
실전에서 매수 지정가가 일부만 체결되고 5분이 지나 잔여를 취소하려다 **실패하면**, 30초마다 도는 「오탐 복구」가 그 주문을 되살리며 `reverse_confirm` 을 부른다. 그런데 그 함수에는 **가드가 0줄**이다(쌍이 되는 `confirm_order` 에는 있다). 그 결과 ①살아 있는 예약을 부분체결 금액으로 덮어쓰고 ②같은 금액을 `reserved` 에 **두 번째로** 더하고 ③넣은 적 없는 금액만큼 **다른 포지션의 invested 를 깎는다**. 정합성 등식이 **약 2×금액** 만큼 깨지고, 탐지 수단은 그날 저녁 EOD 검증 하나뿐인데 그때는 이미 원장이 이중기록돼 있다.

**⑨ 「장 개시·마감 콜백이 8전략 중 첫 전략(elder)에만 간다」** (검수자 신규 발견)
`on_market_open()` / `on_market_close()` 는 `self.strategy`(**단수**)에만 간다 — dict 의 첫 항목, 즉 `elder_ema_pullback` 이다. 09-14 로그가 그대로 증명한다: `장 마감 — 거래 N건` 이 하루 종일 **단 1줄**, 그것도 Elder 다. ⇒ **나머지 7전략은 「장 시작」이라는 이벤트를 받은 적이 없다.** 지금은 매일 07:40 재기동이 이 결함을 가려 왔다. 고도화 중 「장 시작에 뭘 초기화한다」를 넣는 순간 **7전략에서 조용히 안 돈다.**

---

## 2. 단계별 검토

각 단계는 **(a) 실제 흐름 사슬 → (b) 09-14 실측 대조 → (c) 잘 된 것 → (d) 구조적 약점 + 사고 시나리오 → (e) 신규 결함 → (f) 고수 권고 3줄** 고정 형식이다.

---

### ① 매수후보 선정

#### (a) 실제 흐름 사슬

```
main.py:429   while self.is_running
main.py:433     if not is_market_open(): sleep(30); continue        <- 유일 시간 게이트
main.py:438     if not self._candidates_loaded:
main.py:439         await self._load_screener_candidates()          <- ★ 루프 1~5단계 «전부»보다 앞 (순차 await)
        └ bot/candidate_loader.py:44
           ├ :56-60  await liquidation_handler.run_screener_snapshot_hook()   (예외는 warning 으로 삼킴)
           │   └ bot/liquidation_handler.py:591  SCREENER_SNAPSHOT_ENABLED 가드
           │      :596-598  _snapshot_done_date 하루 1회 가드
           │      :604      scan_date = get_previous_trading_day(now)  = D-1
           │      :610-618  run_once(..., max_candidates=MAX_CANDIDATES_PER_STRATEGY)   <- 20
           │         └ runners/screener_snapshot_collector.py:105 build_adapter
           │            :112-115 params=default_params(); params["max_candidates"]=20
           │            :117     params_hash = compute_params_hash(params)      <- ★ 룰 파라미터 미포함
           │            :118     candidates = adapter.scan(scan_date, params)
           │               └ strategies/_rule_screener_base.py:108 base_filter(_load_universe)
           │                  :165 _load_daily  :178 describe_impossible_drop  :136 match  :147-148 score desc [:20]
           │            :138-144 save_screener_snapshot  → db/repositories/candidate.py:139-156 UPSERT
           │
           ├ :63-68  max_candidates 결정                                 <- ★ 20 이 10 으로 깎이는 자리
           ├ :71     if len(strategies) > 1 → :139 _load_candidates_multi_strategy   ← 페이퍼(8전략)
           │   └ core/candidate_selector.py:1010 select_candidates_per_strategy
           │      :1044 _fetch_candidates_for_strategy → :1082-4 screener_snapshot_provider
           │      :1085-93 예외 → fail-closed(그 전략 금일 매수 중단) / :1095-102 0건 → 정상
           │      :1105 _apply_sector_news_rerank (:1148 · shadow · fail-open)
           │      :1130 _filter_unsafe_stocks(pool, limit=max_candidates)   <- 지연 필터링
           ├ :76-128 «단일전략 경로»                                      ← 실전(1전략) ★ 분기점
           │   └ core/candidate_selector.py:130 load_from_screener
           │      :222-229 data/screener_*.json «당일자 파일만» → 없으면 :65 select_daily_candidates(거래량 순위 API)
           ├ :151    should_use_volume_fallback(pool)   ← «전» 전략 0건일 때만 True(:241)
           └ :200    add_selected_stock(..., owner_strategy=폴더키)
                └ core/trading/order_execution.py:112-123 TradingStock(owner=폴더키) → register_stock
                   :130 intraday_manager.add_selected_stock(code,...)   ← owner 없음, 종목코드 «단일키»
                   :136 data_collector.add_candidate_stock(code, name)  ← ② 폴링 대상 등록
```

**페이퍼/실전 분기점** — `bot/candidate_loader.py:71` 의 `len(strategies) > 1`. 페이퍼(8전략)는 `screener_snapshots` 를 읽고, **실전(1전략)은 그 표를 아예 안 읽는다.** 후보 출처가 `data/screener_*.json` 당일자 파일, 없으면 **거래량 순위 API** 다. 전략 진입 룰을 거치지 않은 풀이다.

**문서와 코드가 다른 곳 3건**

| # | 문서·이름이 말하는 것 | 코드의 실제 |
|---|---|---|
| D-①1 | `_verify_screener_snapshot` 의 로그 문구 `EOD 스크리너 스냅샷 실행 완료` | **EOD 에 생성하지 않는다.** 그 함수(`bot/system_monitor.py:715`, `:743-762`)는 플래그를 보고 `SELECT COUNT(*)` 한 줄 찍는 **검증 전용**이다. 09-14 15:35:03 의 `DB 저장 106건` 은 **그날 아침에 넣은 106행을 다시 센 값**(15시대에 `[스냅샷] … 시작` 로그 0건, 경과 1초 미만 vs 아침 16초). |
| D-①2 | 후보의 진실원 = 「전날 EOD 스냅샷」 또는 「당일 09:00 스캔」 | 둘 다 아니다. **「D-1 확정 일봉으로 당일 09:00:2x 에 만든 스냅샷」**이다. |
| D-①3 | 표 `candidate_stocks` 가 후보 진실원 | **죽은 표.** 마지막 행 2026-07-07. 09-14 `07:40:11 오늘(2026-09-14) 후보 종목 없음`. 다중전략에는 **writer 가 아예 없다**(writer 는 단일전략 경로 안 `:93-99`). |

#### (b) 09-14 실측 대조

| 항목 | 실측 |
|---|---|
| 스냅샷 생성 | 09:00:28 시작 → 09:00:44 완료(**16초**), `scan_date = 2026-09-11` |
| DB 재현 | `screener_snapshots` 106행 / 고유 98종목 / 전략 7 / 전략당 해시 1 / `created_at` 09-14 09:00:30~43 |
| 전략별 생성 | elder 20 · envelope 1 · daytrading 20 · minervini 5 · ma20 20 · ma5 20 · rs_leader 20 · deep_mr **0** |
| 전략별 소비 | 10 · 1 · 10 · 5 · 10 · 10 · 10 · 0 = **56** (각 로그 `스냅샷 20건, 목표 10건`) |
| 안전필터 | 58건 조회 → 56 통과. 제외 **2건 전부 VI발동**(488280 · 140430). 거래정지·관리종목·정리매매·판정불가 0, 조회실패 보수적통과 0 |
| 섹터뉴스 재정렬 | 7전략 전부 `mode=shadow reason=ok`, 섹터매핑 결손 0, 이동 0~16종목 |
| 폴백 | `[E6] 🔴` **0건** — 전 전략이 D-1 스냅샷 경로 정상 |
| 등록 | `09:01:02 [E6] 다중 전략 후보 등록 완료: 56종목 (8전략)` |
| 슬롯 경고 | `최대 관리 종목 수(120)에 도달` **0건**(실사용 등록 누계 81, 동시 관리 78) |
| 불가능봉 제외 | 스크리닝 단계 66건(envelope 16 · rs 14 · ma20 11 · ma5 8 · minervini 5 · elder 5 · daytrading 4 · deep_mr 3) |
| `params_hash` DB 재현 | `book_pullback_ma20` 와 `book_pullback_ma5` 가 **동일 해시 `9f2ad26d…`** (검수가 DB 로 직접 재현) |

교차검증: `선정 완료` 45건(09:00 34 + 09:01 11) + 이미 관리 중 11건 = **56** ✅ / 안전필터 조회 58 = 소비 56 + VI 제외 2 ✅

#### (c) 잘 된 것

1. **「없다」와 「고장」을 값으로 갈랐다.** `core/screener_snapshot_provider.py:75-80` 이 예외를 삼키지 않고 올려서, 소비자가 두 사건을 **정반대로** 보고한다 — 고장은 `:1089` ERROR + **그 전략 금일 매수 중단(fail-closed)**, 0건은 `:1098` INFO 정상. `68b542f` 이전에는 둘 다 「다른 명단에서 사오기」였고 고장 로그가 `debug` 였다. **이 축은 구조적으로 옳다.**
2. **지연 필터링으로 슬롯이 안 새게 만들었다.** `_filter_unsafe_stocks(..., limit=)`(`core/candidate_selector.py:699-733`)는 「자른 뒤 거르기」가 아니라 **「안전한 후보가 N개 모일 때까지만 조회」**다. 09-14 daytrading 실측: 12건 조회 → 10건 확보(VI 2건 제외)로 **10칸을 다 채웠다**.
3. **재정렬(섹터뉴스 shadow)을 진짜 장식으로 만들었다.** `_apply_sector_news_rerank`(`:1148`)는 **import 문까지 outer try 안**에 두고(`:1175`) 어떤 실패도 「원래 순서 + WARNING + 기록행」으로 끝낸다. 호출 지점이 양쪽 try 바깥이라는 **위치 근거까지 주석에 남겼다**(`:1156-1165`). shadow 관측 중인 축에서 이 정도 격리는 모범이다.
4. **안전필터의 값 계약을 문서가 아니라 실측으로 못 박았다**(`:493-521`). `ssts_yn`·`mang_issu_yn` 같은 지뢰를 「고쳐서 되돌리지 말 것」으로 고정했고, 실패(None)는 **캐시하지 않는다**(`:596-599`).

#### (d) 구조적 약점 + 「이대로 두면 어떤 사고」

**약점 ①-1 — 후보 상한의 SSOT 가 두 개다.**
`config/constants.py:200` 은 스스로 「EOD 스냅샷 생성·라이브 소비 **공통 SSOT**」라 선언하는데, 소비 쪽은 `bot/candidate_loader.py:63-68` 에서 `config.strategy.parameters.max_candidates` 로 덮인다. 그 값의 출처는 **비활성 `sample` 전략**이다.
> **사고 시나리오** — 3전략 고도화에서 「후보 폭을 20으로 넓혔다」고 믿고 백테스트한다. 라이브는 계속 10이라 **재현이 안 되는데 원인이 보이지 않는다**(로그는 정상, 경고 0건). 반대로 상한을 맞추는 1줄 수정을 하면 관리 종목이 **120 한도를 처음으로 넘겨**(추정 약 126) 마지막 등록 전략(순서상 `rs_leader`)의 후보가 통째로 안 들어간다. 증상은 WARNING 한 줄뿐이고 「매수 0건」은 「신호가 없었다」와 구별되지 않는다. **두 상수는 한 몸이다.**

**약점 ①-2 — 「룰을 안 바꿨다」의 기계적 증거가 없다.**
`params_hash` 가 `default_params()` 만으로 계산되는데(`runners/screener_snapshot_collector.py:117`), ma20/ma5/envelope 세 스크리너는 `match(df, params)` 의 `params` 를 **한 번도 안 쓴다**. 그래서 **서로 다른 룰이 같은 해시**를 쓴다(DB 재현). 게다가 `base_filter` 는 인자로 params 를 안 받고 내부에서 `default_params()` 를 다시 읽으므로, **호출자가 넘긴 오버라이드가 적용되지 않은 채 `params_json` 에는 기록된다** — 기록이 거짓이 된다.
> **사고 시나리오** — ma20 룰 상수를 바꾼다 → 해시 불변 → `get_snapshot_date_range(params_hash=None)` 이 변경 전후 행을 **한 덩어리로** 돌려준다 → 사전등록의 「집합 차분으로 회귀 판정」이 성립하지 않는다. **3전략 고도화의 모든 집합 차분 주장이 기계적 근거를 잃는다.** 그리고 해시를 고치는 날 곧바로 다음 결함이 발화한다 — 소비 쪽 상위 N 절단이 랭크가 아니라 **해시 순**(`db/repositories/candidate.py:226 ORDER BY scan_date, params_hash, rank_in_snapshot`)이라 「구 파라미터 전량 → 신 파라미터 앞부분」이 된다.

**약점 ①-3 — 장 시작 첫 34초가 감시 공백이다.**
`run_once`(`runners/screener_snapshot_collector.py:82`)는 **동기 함수**인데 `bot/liquidation_handler.py:610` 이 `to_thread` 없이 async 안에서 직접 부른다(같은 레포가 `bot/system_monitor.py:236,322,356,560,651,894` 에서는 `asyncio.to_thread` 를 **잘 쓰고 있다** — 여기만 안 쓴다). 그 사이 루프 1~5단계(`collect_once` · `check_pending_orders_once` · **`check_positions_once`(손절 감시)** · `on_tick` · EOD)가 **한 번도 안 돈다**.
> **사고 시나리오** — 09-14 같은 갭다운 개장일(보유 36 · 손절 9건 중 3건이 밤새 갭), 09:00:28~09:01:02 사이에 급락하는 보유 종목이 생겨도 **첫 손절 판정은 09:01:02 이후**다. 실탄 전환 후 종목당 금액이 커지면 이 34초가 그대로 돈이다.
> 🔴 **주의 — 처방이 직관과 다르다.** `to_thread` 로 내려도 **안 고쳐진다.** `main.py:438-440` 이 후보 로드를 메인 루프 1~5단계보다 **앞에서 순차로 await** 하기 때문이다. 스레드로 내리면 살아나는 것은 **시스템모니터·텔레그램 태스크**뿐이다. 유효한 처방은 **08:5x 장전에 스냅샷을 만들고 09:00 엔 읽기만** 하는 분리 하나다.

**약점 ①-4 — 「하루 1회」를 되돌리는 운영 경로가 없다.**
`reload_candidates`(`bot/candidate_loader.py:22`) 실호출자 **0건**(코드 안 TODO 가 스스로 그렇게 적어 뒀다 `:32-36`). `_candidates_loaded` 를 False 로 되돌리는 경로도 **프로세스 재기동뿐**. `_safety_info_cache`(`core/candidate_selector.py:54`)도 `clear_safety_cache` 호출자가 죽은 메서드 하나뿐이라 **프로세스 수명 내내 09:00 판정이 고정**된다.
> **사고 시나리오** — 지금은 매일 07:40 재기동이 가려 주지만, 「상주시키자」는 결정이 내려지는 순간 **장중에 거래정지가 지정된 종목이 후보로 살아남는다.** 같은 뿌리가 ③의 `daily_trades` 영구 누적(→ 전략 영구 매수불능)으로도 나타난다.

#### (e) 신규 결함

| # | 결함 | 위치 | 모드 | 검수 판정 | 심각도 |
|---|---|---|---|---|---|
| **X4** | 후보 상한 이중화(생성 20 / 소비 10, 출처 = 비활성 `sample` 파라미터) | `bot/candidate_loader.py:63-68` ↔ `config/constants.py:200` ↔ `config/trading_config.json:22-29` | 페이퍼(실전은 같은 줄이 `load_from_screener(10)`) | **CONFIRMED** | P2 |
| **X5** | `params_hash` 가 룰 파라미터 미포함 → ma20/ma5 **동일 해시**(DB 재현) · 집합 차분 무력 | `runners/screener_snapshot_collector.py:117` · `strategies/_rule_screener_base.py:136` · 각 `screener.py` | 공통 | **CONFIRMED(DB 재현)** | P2 |
| **X18** | X4 를 고치면 `MAX_MANAGED_STOCKS=120` 을 처음으로 넘김(조건부 결합) | `config/constants.py:91` ↔ `core/intraday_stock_manager.py:105-107` | 공통 | ~~P2~~ → **P3** · 결합은 실재, 수치(약 126)는 **추정**. 「아직 일어나지 않은 변경의 하류」 | P3 |
| **X19** | `candidate_stocks` 복원이 `owner_strategy` 를 안 넘김(같은 파일 `:569` vs `:646` **비대칭**) | `bot/state_restorer.py:535, 569-574` | 실전 | 위치 CONFIRMED / ~~「다중 진입」 시나리오~~ **OVERSTATED** — 1계좌1전략에 「서로 다른 전략」이 없다. 오히려 owner 빈 슬롯은 그 하나뿐인 전략에 **보인다** ⇒ P1-2 의 **우연한 완화** | P3 |
| **X20** | 후보 `name` 이 영원히 종목코드(`후보 제외: 488280(488280)`) | `strategies/_rule_screener_base.py:189` → `core/candidate_selector.py:1113` | 공통 | **CONFIRMED** · 실탄 후 경보 가독성 | P3 |
| **X6b** | 다중 해시가 생기면 상위 N 절단이 랭크가 아니라 **해시 순** | `db/repositories/candidate.py:226` | 공통 | **CONFIRMED(잠복)** · X5 를 고치는 날 즉시 발화 ⇒ **한 묶음 처리(M6)** | P3 |

**시나리오·재현법·수정안(제안)**

- **X4** — 재현: `python -c "from utils.price_utils import load_config; c=load_config(); print(type(c.strategy), c.strategy.parameters.get('max_candidates'))"`(실행 금지, 경로만 명시). 수정안: `bot/candidate_loader.py:71` 다중분기 **앞**에서 `max_candidates = MAX_CANDIDATES_PER_STRATEGY` 를 강제하고 `:63-68` 파생은 단일전략 경로로만 내린다. **단 X18 과 같은 결재**로 묶어야 한다.
- **X5** — 재현: DB `SELECT strategy, params_hash, count(*) FROM screener_snapshots WHERE scan_date='2026-09-11' GROUP BY 1,2` (SELECT 만). 수정안 3안: (a) `base_filter(self, universe, params)` 로 시그니처 통일 (b) 룰 kwargs 를 `default_params()` 에 전부 노출 (c) 최소 조치로 `params_json` 에 `rule_module`+`strategy_name` 을 넣어 **해시를 전략별로 분리**. 셋 다 **고도화 착수 «전»에 하는 것이 싸다**(해시가 바뀌면 과거 행과 단절되므로 사전등록 필수).
- **X19** — 수정안: `:569` 에 `owner_strategy=` 명시, 또는 이 복원 블록을 다중전략 모드에서 **비활성 선언**. 살아남는 지적은 ①같은 파일 두 복원 경로의 비대칭 ②표는 죽었는데 reader 는 살아 있는 **감사 함정**이다.
- **중복 참조** — 기존 **P2-26**(실전도 `screener_snapshots` 에 쓴다 · 인스턴스 컬럼 없음 · 읽기는 전 해시 합산) **여전히 그렇다**. 기존 **P1-2**(단일전략 owner=클래스명 → 매수 0건) **여전히 그렇다** — 이 단계에서는 「`get_selected_stocks(폴더키)` 가 0건 반환」으로 나타난다. 기존 **P2-25**(일일 리셋 경로 부재) **여전히 그렇다**.

> 🔑 **결재문에 반드시 들어가야 할 한 줄**(검수 §5-3 이 「3편 중 이 지적이 가장 값지다」고 평가):
> **「실전 후보의 출처는 스크리너 스냅샷이 아니라 당일자 JSON 또는 거래량 순위 API 다.」**
> P1-2(A3 한 줄 수정)를 적용해도 **owner 라벨만 고쳐지고 출처는 그대로**다. **전략 룰을 거치지 않은 풀**이라 3전략 고도화의 전제와 다르다.

#### (f) 고수 권고 3줄

| 층 | 권고 |
|---|---|
| **지금 당장** | 후보 축은 **동작 0 변경으로 얻을 것이 별로 없다.** 대신 ③의 I1(차단 로그에 종목·전략) 패스에 **`add_selected_stock` 실패를 전략 단위로 집계해 ERROR 1줄**(어느 전략이 몇 칸 못 받았는가)을 얹어라 — X18 이 터질 때 유일하게 보이는 신호가 된다. |
| **실전 전환 전** | ①**스냅샷 훅을 08:5x 장전 1회로 분리**(09:00 엔 읽기만) — 34초 공백이 없어진다. 실행 시각 변경이므로 **사전등록** 대상. ②결재문에 **「실전 후보 출처 = 당일자 JSON/거래량 순위」**를 명시. |
| **장기** | `params_hash` 를 **「생성물을 결정하는 모든 입력」의 함수**로 만들고(X5+X6b 한 묶음), 후보 상한을 상수 하나로 통일해 `MAX_MANAGED_STOCKS` 와 **같은 결재**에 묶는다(X4+X18). 이 둘을 안 하면 3전략 고도화의 「집합 차분」 주장이 **기계적 근거를 못 갖는다**. |

---

### ② 데이터 수집

#### (a) 실제 흐름 사슬

```
[현재가 — 3초 루프의 실체]
main.py:422  LOOP_INTERVAL = 3
main.py:449  await self.data_collector.collect_once()
 └ core/data_collector.py:226-231 → :113 for code in config.data_collection.candidate_stocks  ← «후보 전량»
    :115-120 asyncio.gather(_collect_stock_data)
    :141-147 run_with_timeout(executor(max_workers=4), _get_current_price_sync, timeout=15)
    :186     broker.get_current_price → framework/broker.py:362 get_inquire_price (TR 실조회)
    :151-168 float 반환 ⇒ OHLCVData(open=high=low=close=price, volume=0)     ← ★ «가짜 봉»
 └ core/models.py:75-82 Stock.add_ohlcv — last_price 갱신 + 리스트 «1000개» 상한
 └ api/kis_auth.py:50-52, 629-647  전역 threading.Lock + API_CALL_INTERVAL=0.10  ← 모든 호출 직렬화
 └ main.py:513-517  sleep = max(0, 3 − elapsed)   ← 실측 «항상 0»

[일봉 — 전략이 generate_signal 에서 보는 것]
strategies/base.py:612-614 → core/trading_context.py:196 price_repo.get_daily_prices(days=120)
 └ db/repositories/price.py:159-165  SELECT ... (volume*COALESCE(adj_factor,1))   ← volume 에만 곱함
 └ core/trading_context.py:197 _drop_unconfirmed_today_bar(:143-174)   ← ★ no-lookahead 단일 지점
 └ strategies/base.py:645 describe_impossible_drop → :660 generate_signal(timeframe='daily')
[일봉 쓰기 W1] core/intraday_stock_manager.py:133 → core/intraday/data_collector.py:47 collect_daily_data_only
 └ :68 broker.get_ohlcv_data(code,"D",150) → :88 db/repositories/price.py:64 save_daily_prices_batch
    :113-126 past_rows_insert_only=True  ← 과거행 INSERT-only / «오늘행만» UPSERT

[분봉] config/trading_config.json:101 "rebalancing_mode": true
 └ core/intraday_stock_manager.py:132-134 → collect_daily_data_only  ⇒ 장중 분봉 «0건»
[죽은 사슬] core/intraday/realtime_updater.py:326 batch_update_realtime_data  ← 프로덕션 호출자 0
 └ :357 _update_current_price_data(→ current_price_info 영원히 빈 값)  :368 check_data_quality ← 유일 진입점
 └ core/intraday/price_service.py:73-89 get_cached_current_price — docstring 이 스스로 「항상 None」 선언
```

**「전일 확정봉이 장중에 갱신되는 순간」의 답** — D-1 행은 **장중에 갱신되지 않는다**(W1 가드가 과거행 INSERT-only). 대신 **당일(D) 행이 09:00 에 생성(UPSERT)** 되고, 읽기 계층이 그 당일 행을 **매번 잘라낸다**. ⇒ 전략이 보는 마지막 봉은 **장중 내내 D-1 종가로 고정**이다(08-13 결론과 일치, 이번에 줄 단위로 기전 확정).

**이 폴링을 «누가» 읽는가 — 전수 재현**
grep 조건: `core/ bot/ api/ framework/ db/ strategies/ utils/ runners/ collectors/ tools/ main.py` 에서 `data_collector\.(get_stock|get_candidate_stocks|get_all_stocks|has_stock)`

| # | 위치 | 대상 상태 | 용도 |
|---|---|---|---|
| 1 | `core/trading/position_monitor.py:155` | **POSITIONED 만** | 미실현손익 표시 |
| 2 | `core/trading/position_monitor.py:343-356` | **POSITIONED 만** | 전략 매도신호용 «분봉» DataFrame |
| 3 | `core/trading/position_monitor.py:402` | **POSITIONED 만** | 현재가 3순위 폴백 |
| 4 | `bot/system_monitor.py:840-841` | 전체 | 상태 로그 카운터(관측만) |

**정확히 4건, 3건이 POSITIONED 전용.** 매수 경로는 `ctx.get_current_price` 를 쓰는데 1순위 캐시가 **구조적으로 항상 None** 이라 매번 broker 실조회로 떨어진다 — data_collector 를 안 본다.

#### (b) 09-14 실측 대조

| 항목 | 실측 |
|---|---|
| 폴링 라운드 | `시스템 상태` 종목 카운터(`232140`) 46→194→342→494→643→787→933→1000. 30분(1800초) 증분 **148·148·152·149·144·146** ⇒ **약 12.2초/라운드** (3초 아님) |
| 라운드 산술 | 폴링 78 + 보유 33 ≈ 111 호출 × 0.1초 = 11.1초 (실측 12.2초) ⇒ **라운드 시간은 호출수에 선형** |
| 카운터 포화 | 12:10~12:40 사이 전 종목 **1000 고정** = `core/models.py:81-82` 리스트 상한 |
| API 총계 | **237,141회** · 성공률 99.92% · 속도제한 **173회**(0.07%) |
| 동시 관리 | 09:10:41 `시스템 상태` 수집 dict **78종목**(등록 누계 81 − 09:04~05 매도 3) |
| 일봉 수집 | `일봉 데이터만 수집 (리밸런싱 모드)` **78건**, 각 101개, `DB 저장 완료` 78건 |
| 분봉 | 장중 **0건**. `전체 거래시간 분봉 데이터 수집 시작` 300건 전부 **15:46 이후**(EOD 배치 112,926행) |
| 품질검사 | `데이터 품질`·`data_quality`·`품질`·`quality` **0건**(대소문자 무시) — 「안 찍혔다」가 아니라 **「돌 수 없다」** |
| 현재가 결측 | `현재가 정보 없음` **9건 · 고유 9종목 · 전부 15:38~15:44**(장중 0건) ⇒ 장중 매매 영향 없음 |
| ERROR / WARNING | ERROR **10**(결측 9 + 외국인수급 0행 1) / WARNING **329**(속도제한 173 · 불가능봉 66 · 장시간외 추가보류 36 · rs_leader shadow 38 · 기타 16) |
| 웹소켓 | `websocket|웹소켓|실시간` **0건** — 스트리밍 경로 없음, 전량 폴링 |

> ⚠️ **검수 정정** — 원문 A 의 「API 예산 100% 포화(10.1 호출/초)」는 **근거로 쓰지 말 것**. 237,141회를 「장중 23,400초」로만 나눈 값인데 봇은 07:40~18:34 가동이고 15:46 이후 EOD 분봉 배치가 **같은 카운터에 들어간다**. 살아남는 검증된 문장은 **「라운드 시간이 호출수에 선형이다」** 뿐이다.

#### (c) 잘 된 것

1. **단계 격리가 옳은 극성이다.** `main.py:444-508` 이 5단계를 각각 try 로 감싸 **「수집 실패가 EOD 청산을 막지 않는다」**를 보장한다.
2. **`adj_factor` 방향 규약을 읽기 계층에 단일화했다.** `db/repositories/price.py:146-153` · `db/quant_daily_reader.py:83-91` · `strategies/historical_data.py:162-178` 이 **전부 같은 문구**로 「가격엔 안 곱한다 / volume 엔 곱한다」를 못 박고 **기계검사까지** 걸어 뒀다. 세 파일이 독립 구현인데도 값이 안 갈리는 이유가 이 문서화다.
3. **속도제한 백오프를 전역 락 «밖»에 뒀다.** `api/kis_auth.py:491` 의 `time.sleep(wait_time)` 은 `_api_lock`(`:634`) 안이 아니다 — **한 종목의 백오프가 전 시스템을 얼리지 않는다.** 173회 발생에도 성공률 99.92% 가 나온 구조적 이유다.
4. **W1 쓰기 가드의 경계를 「오늘」로 명시했다**(`db/repositories/price.py:113-118`). 「과거를 고치는 도구」와 「최신 봉을 넣는 훅」을 **한 함수에서 극성 반대로 분기**하고 롤백 스위치를 상수 하나로 고정했다.

#### (d) 구조적 약점 + 「이대로 두면 어떤 사고」

**약점 ②-1 — 폴링 대상과 소비 대상이 다르다.**
폴링은 **후보 전량**(09-14 약 78~81종목), 읽는 곳은 **POSITIONED 33~36 전용 3곳**. ⇒ 약 45종목분(**약 56%**)의 호출이 `Stock.ohlcv_data` 에 쌓이기만 하고 **아무도 안 읽는다**. 라운드당 약 4.5초.
> **사고 시나리오** — 실탄 전환 후 손절이 급한 순간, 그 종목의 `inquire-price` 는 **아무도 안 읽을 45건 뒤에** 전역 락 순번을 받는다. 후보를 늘리거나 전략을 추가하면 라운드가 12초→18초로 늘고 **손절 감시 주기가 선형으로 나빠지는데, 그 지연의 출처는 「아무도 안 읽는 폴링」이다.**

**약점 ②-2 — 「분봉」이라 부르는 것이 분봉이 아니다.**
`core/trading/position_monitor.py:341-361` 이 `pd.DataFrame(price_data.ohlcv_data)` 를 만들어 `generate_signal(..., timeframe='intraday')` 에 넘긴다. 그 행들은 **O=H=L=C=현재가 · volume=0 · 간격 12초 · 최근 1000개(약 3.4시간)**다. 진짜 분봉은 `rebalancing_mode=true` 라 **비어 있다**. 게다가 이 경로는 `describe_impossible_drop` 과 `_drop_unconfirmed_today_bar` **가드를 둘 다 우회**한다.
> **사고 시나리오** — 어떤 전략이 intraday 매도 룰에 거래량·봉 실체·고저폭을 쓰는 순간 그 룰은 항상 「volume=0, 몸통=0」을 본다 ⇒ 조용히 **항상 False(또는 항상 True)**. 이 프로젝트의 재사용 규칙 **「한 번도 발동 안 함 ≠ 막혀 있다」**가 정확히 여기 걸린다. 실탄에서는 **매도 누락**으로 나타난다.
> 🔑 이것은 ④의 B-7(가드 위치가 3파일에서 다름)과 **같은 결함의 서로 다른 절반**이다 — **한 수정으로 둘 다 닫힌다**(M2 · I5).

**약점 ②-3 — 폴백 3단이 실은 1단이다.**
`core/trading/position_monitor.py:373-409` 의 현재가 3단 폴백 중 2단(`get_cached_current_price`)은 **구조적으로 항상 None**, 3단(`data_collector.get_stock`)은 1단과 **같은 API 를 12초 전에 부른 값**이다. ⇒ KIS `inquire-price` 가 죽으면 **세 단이 동시에** 죽는다. 「폴백이 있다」는 착시만 남는다.

**약점 ②-4 — 품질 가드가 도달 불가인데 「있는 것처럼」 보인다.**
`core/intraday/data_quality.py` → 유일 호출 `core/intraday/realtime_updater.py:368` → 그 함수의 프로덕션 호출자 **0**. 파사드 `core/intraday_stock_manager.py:203-205, 422-424` 가 **public 메서드로 노출**돼 있어 코드를 읽으면 살아 있어 보인다.
> ⚠️ **검수 하향** — 「감사 함정」 프레이밍은 절반만 맞다. **레포가 이미 자기 주석 3곳에 적어 뒀다**(`core/intraday/price_service.py:83-89` 「항상 None」 · `core/post_market_data_saver.py:11` · `bot/system_monitor.py:387`). 남는 지적은 **「파사드가 public 인데 주석은 안쪽에만 있다」**로 한정된다. **신규로 세지 말 것.**

#### (e) 신규 결함

| # | 결함 | 위치 | 모드 | 검수 판정 | 심각도 |
|---|---|---|---|---|---|
| **X6** | 폴링 대상(후보 전량) ≠ 소비(POSITIONED 3곳) → 라운드 12.2초 · **감시 지연이 후보수에 선형** | `core/data_collector.py:113` ↔ `core/trading/order_execution.py:136` ↔ 소비 3곳 | 공통 | **CONFIRMED**(라운드 산술 재현 · 단 「예산 100% 포화」 수사는 기각) | P2 |
| **X7** | 매도 판단이 `O=H=L=C·volume=0` 「가짜 분봉」을 보고, **minervini·daytrading 만 그 경로가 열려 있다** | `core/trading/position_monitor.py:341-361` + `core/data_collector.py:151-168` + 두 전략 가드 위치 | 공통 | **CONFIRMED** · A-N8 + B-7 **병합(M2)** | P2 |
| **X21** | 연속 실패 경보에 쓰로틀이 없다(`count >= 5` 이면 **라운드마다** WARNING, 4회까지는 흔적 0) | `core/data_collector.py:128-131` | 공통 | **CONFIRMED(잠복 · 09-14 발화 0)** | P3 |
| **X22** | 속도제한이 전역 간격을 자동 상향하지 않는다(AIMD 부재) | `api/kis_auth.py:481-492` ↔ `:663-667`(수동 API, 운영 호출자 0) | 공통 | **CONFIRMED** | P3 |
| **X23** | `data_quality` 죽은 사슬 — 파사드는 public, 주석은 안쪽 3곳 | `core/intraday_stock_manager.py:203-205, 422-424` → `core/intraday/realtime_updater.py:368` | 공통 | ~~「신규 감사 함정」~~ → **CONFIRMED 이나 신규 아님**(레포가 이미 문서화) | P3 |

**시나리오·재현법·수정안(제안)**

- **X6** — 재현(실행 금지): `core/trading/order_execution.py:136` 의 등록 시점을 POSITIONED 전이로 옮긴다고 가정하고 `len(config.data_collection.candidate_stocks)` 를 EOD 상태로그의 POSITIONED 수와 대조. 수정안: `add_candidate_stock` 을 **체결 시점(POSITIONED 전이)** 으로 옮기고 SELECTED 는 폴링에서 뺀다. 매수 판단은 이미 `ctx.get_current_price` 실조회라 **동작 불변**. 예상 효과 12.2초 → 약 7초(추정). **관측치가 바뀌므로 사전등록.**
- **X7** — 수정안 2안 중 **검수 권고는 ②**: `core/trading/position_monitor.py:341` 에 `exit_timeframe != "intraday" → return` **1줄**. 라이브 8전략이 전부 `daily` 라 **동작 변경 0**이고 **전략 룰 파일을 안 건드려 6주 동결과 무관**하다. (B 의 원안 ①「두 전략 파일의 가드를 3줄 이동」보다 이쪽 — 그건 룰 파일 수정이다.)
- **X21** — 수정안: 이미 `:23` 에서 쓰고 있는 `RateLimitedLogger` 경로로 옮기고, EOD 에 **집합 차분**(어제 실패집합 vs 오늘)으로 1줄 요약. 🔑 이 프로젝트가 이미 겪은 「경보 마비」 유형이고, **「EOD 점검은 건수가 아니라 집합 차분으로」**라는 기존 규칙과 같은 축이다.
- **중복 참조** — 기존 **08-13 「슬롯 80 = API 호출 예산」** 여전히 그렇다(80→120, 실사용 81). 기존 **「`rebalancing_mode=true` → 일봉만 수집」** 여전히 그렇다(장중 분봉 0건 실측).

#### (f) 고수 권고 3줄

| 층 | 권고 |
|---|---|
| **지금 당장** | `core/trading/position_monitor.py:341` 에 **`exit_timeframe` 조건 1줄**(X7). 8전략 전부 `daily` 라 **동작 변경 0**인데, A-N8(쓰레기 입력)과 B-7(가드 위치 비대칭)을 **동시에** 닫는다. 이 검토에서 비용 대비 효과가 가장 큰 1줄 중 하나. |
| **실전 전환 전** | 「폴백 3단이 실은 1단」(약점 ②-3)을 결재문에 명시하라 — **KIS 단건 조회가 죽으면 손절·상한가 가드·EOD 매도가가 동시에 죽는다**. 자매 문서 정정 3과 같은 사실이다. |
| **장기** | 폴링을 **POSITIONED 로 좁히고**(X6) `시스템 상태` 블록에 **계기 3종**(라운드 소요 · 라운드당 호출수 · POSITIONED 감시 지연)을 넣어라. 그러면 X6·X22 가 **숫자로 보인다**. 죽은 사슬 3개(`start_collection`·`batch_update_realtime_data`·`DataQualityChecker`)는 지울지 되살릴지 그때 결정한다(X23). |

---

### ③ 매수 진입

#### (a) 실제 흐름 사슬

```
[라운드로빈] main.py:418-517
 :429 while is_running  :433 is_market_open() 단일 게이트  :437 _candidates_loaded 최초 1회
 :448 [1/5] collect_once   :454 [2/5] check_pending_orders_once   :460 [3/5] check_positions_once(④ 백스톱)
 :466 [4/5] on_tick        :504 [5/5] _check_eod_liquidation      :513-517 sleep = max(0, 3 − elapsed)  ← 항상 0
 :467-471 idx = (iteration // 3) % len(strategy_names)   ← ON_TICK_EVERY_N=3
 :484 ctx = ctx_for_strategy(name)   :486-489 asyncio.wait_for(strat.on_tick(ctx), timeout=30)

[전략 매수 루프] strategies/base.py:612-686
 :612 for stock in ctx.get_selected_stocks()        ← owner 격리 있음(trading_context.py:273-298)
 :614 ctx.get_daily_data(days=OHLCV_LOOKBACK_DAYS=120)   :645 describe_impossible_drop
 :660 self.generate_signal(code, data, timeframe="daily")   :686 await ctx.buy(code, signal=signal)

[ctx.buy 가드 14겹] core/trading_context.py:313-536
 1 :333 시장 CB   2 :346 resolve_regime_index("auto" 해석)   3 :351 급락게이트   4 :359 국면게이트(PIT 일봉)
 5 :369 _get_own_trading_stock(폴더키→클래스명→코드단독)     6 :379 중복 소유권(POSITIONED/BUY_PENDING)
 7 :395-405 VI arm 조회(예외는 WARNING 후 «통과»)            8 :417 종목 VI       9 :422 일일 손실 한도
 10 :439 매수스톱(entry_min_price)   11 :449 EOD 청산시각 이후 — «intraday 전략만» 차단
 12 :470 상한가 접근(0.25)          13 :488 사이클당 신규진입 ≤ 3   14 :498 종목간 쿨다운 60초
 → :514 analyze_buy_decision(ts, signal, strategy_name=_strategy_key)
 → :521-525 «체결됐을 때만» 쿨다운/사이클 카운터 무장

[자금 예약·수량] bot/trading_analyzer.py:103-366
 :127 전역 POSITIONED 재확인(owner 무관)  :133 25분 매수 쿨다운  :139 일봉 days=140 «재조회»  :144 최소봉
 :162 엔진 판정  :174-176 거절 INFO(10분 쓰로틀)  :185 수량>0  :249-251 reserve_funds(make_reserve_id(code,owner))
 → :275 «페이퍼»  /  :343 «실전»                      ★ 모드 분기점

[매수가·수량 SSOT] core/trading_decision_engine.py:325-435
 :351 check_market_direction (ctx.buy 와 이중 호출 · 60초 캐시)   :367 owner_signal 신뢰(재판정 안 함)
 :403 current_price = _get_live_price(code)   ← 온디맨드 API → 캐시 → 브로커. «일봉 종가 폴백 금지»
 :404 None 이면 "현재가 미확보 — 진입 보류"    :409 price = round_to_tick(current_price)  ← ★ 이것이 「매수가」
 :412-418 밴드 검증(신호의 entry_min/max vs 실시간 price)
 :420-423 페이퍼 get_max_quantity(price, strategy_name=폴더키)  /  :425-427 실전 max_amt=_get_max_buy_amount(); qty=int(max_amt/price)
 실전 발주 → core/trading/order_executor.py:206-212 order_price=int(round_to_tick(price)) → place_buy_order  ← «지정가», 타임아웃 300초
```

**🔑 「매수가」 질문의 답 = 현재가다.** 신호가(D-1 확정 종가)도 밴드도 아니다. 밴드는 **가부 판정에만** 쓰이고 가격에는 관여하지 않는다. ⇒ **실전 지정가는 「판단 순간의 현재가」**라 오르는 중엔 안 붙고 내리는 중엔 붙는다 = **역선택**. 메모리의 「라이브는 돌파 후 밀린 것만 산다」와 같은 기전이 **가격 산정 단계에서 한 번 더** 작동한다.

**문서와 코드가 다른 곳 2건**

| # | 문서·브리프가 말하는 것 | 코드의 실제 |
|---|---|---|
| D-③1 | 「`strategies/base.py.on_tick` 이 `_check_buy`/`_check_sell` 를 부른다」 | **`BaseStrategy` 에 그런 메서드가 없다**(`grep -n "_check_buy" strategies/base.py` = 0건). 실제는 `on_tick` 인라인 루프 2개(매수 `:612-686` · 매도 `:691-713`)이고, `_check_buy`/`_check_sell` 는 **각 전략 클래스의 private 헬퍼**다. **「프레임워크가 부른다」가 아니라 「전략이 자기 `generate_signal` 안에서 분기한다」 — 소유 주체가 정반대다.** |
| D-③2 | 「상태 전이 규칙(`_VALID_TRANSITIONS`)이 불변식이다」 | **권고일 뿐이다.** `core/trading/stock_state_manager.py:207-218` 이 위반 시 `[비정상 상태전이]` **WARNING 만 찍고 그대로 전이한다.** `COMPLETED: [SELECTED]` 뿐인데도 `COMPLETED → POSITIONED` 를 요청하면 **실행된다.** 09-14 위반 0건은 **불변식이 아니라 관측치**다. |

**예외가 삼켜지는 곳** (관측 가능성 축)

| 위치 | 삼키는 것 | 영향 |
|---|---|---|
| `core/trading_context.py:534-536` | `ctx.buy` 전체 → error + None | 매수 「실패」와 「거부」 구분 불가(단 쿨다운 미무장이라 다음 틱 재시도) |
| `core/trading_context.py:406-414` | VI arm 조회 실패 → **WARNING 후 매수 계속** | 의도적(주석 명시) · 보수적 통과 |
| `core/trading_context.py:219-221` | `get_daily_data` 예외 → **debug** + None | **DB 장애가 「데이터 없음」으로 보인다** |
| `bot/trading_analyzer.py:332-333` | 가상매수 상태변경 예외 → **debug** | 주석이 스스로 인정 — `change_stock_state` 는 매칭 0 이면 **조용히 return** 하므로 이 try/except 는 **무력** |
| `core/trading_decision_engine.py:222-225` | 급락게이트 API 실패 → **fail-open(매수 허용)** + WARNING | 의도적 |
| `core/trading/stock_state_manager.py:196-200` | **매칭 0 이면 예외도 반환값도 없이 return** | 🔴 상태 전이 실패가 **관측 자체가 안 됨**. 주석에 2026-08-06 사고 기록(당일 매수 9건 SELECTED 잔류, 청산 대상 46 vs 실보유 55) |

#### (b) 09-14 실측 대조

| 항목 | 실측 |
|---|---|
| **on_tick 주기** | 전략당 **79~80회**(8전략 전부). 09:02~15:28 ≈ 23,200초 ⇒ **약 290초/전략**. ~~72초~~ 는 명목값이고 실측과 **약 4배** 어긋난다. 검산: 라운드 12.2초 × `ON_TICK_EVERY_N` 3 × 8전략 = **293초** ✅ |
| 신호 재생성 | Elder `000660` 매수신호 **79회**, 전부 동일 문자열(D-1 확정봉 고정이므로) |
| **3전략 캡 상태** | ma20 `[sync_positions] 5` / `max_positions: 5`(config.yaml:35) ⇒ **07:40 복원 시점에 이미 포화** · minervini **3/3** 동일 · daytrading 4 → 09:02:21 `0015S0` 매수로 **5/5 포화** |
| ma20·minervini 매수 판정 로그 | **0건.** 하루 종일 `[on_tick] 매수검토 9종목(스킵 0), 신호 0건`(ma20) · `3종목 … 0건`(minervini) |
| 결정적 증거 | `203650` 은 09:02:20 에 룰이 **성립**했고(`close=2620 prior20_high=2290 vol=51031918/838237`) 진입 밴드에서만 떨어졌다. 그런데 09:07:26 이후 전부 `generate_signal None 반환` — **룰이 바뀐 게 아니라 캡이 닫힌 것** |
| 첫 매수 전 과정 | 09:02:20~21 `[PAPER] 매수 시그널: 0015S0 @ 7,900 (추천 379주)` → `가상 매수: 0015S0 **247주 @7,940원**` → `selected → buy_pending → positioned`. **추천 379주(전략 metadata)는 아무도 안 쓴다**; 사이징 SSOT 는 VTM |
| 매수가 검증 | 신호가 7,900 ≠ 체결가 **7,940**(= 현재가). 밴드 7,900×1.03=8,137 ≥ 7,940 통과 |
| 밴드 차단 | `203650` 09:02:21 `[매수거절] 진입가 밴드 이탈 — 스킵 (현재가 2,775 > 상한 2,699)`. 하루 밴드 거절 **5건** |
| 급락게이트 | `ctx.buy` 차단 **713회**(09시 244 · 10시 253 · 11시 13 · 13시 70 · 14시 91 · 15시 42). `[시장방향성필터] 관측` KOSPI 차단 **79** / 허용 28, KOSDAQ 허용 1. 임계 KOSPI −2.5% / KOSDAQ −3.0% |
| `auto` 축 발효 확인 | daytrading 이 `203650`(KOSDAQ)에 **KOSDAQ 임계 −3.0%** 를 적용해 −2.44% 를 **허용** ⇒ 09-11 저녁 머지 `9ab3c37` **의도대로 발효** |
| 국면게이트 | 하루 **1회만** 평가 — `11:05:10 [국면게이트] KOSPI 현재 국면: SIDEWAYS (close 266봉, breadth=무)`. `exclude_bear` 3전략 차단 **0건** |
| 이상징후 | `[비정상 상태전이]` 0 · `[모호조회]/[모호상태변경]/[모호해제]` 0 · `on_tick 타임아웃` 0 · `중복 매수 주문 방지` 0 · `보유 중인 종목 매수 신호 무시` 0 · Circuit Breaker 0 · `이번 사이클 신규 진입` **0건** · `쿨다운 … 남음` 8건 |

> 🔑 **국면게이트 0건은 버그가 아니라 «순서»의 결과다.** `ctx.buy:351` 급락게이트가 먼저 떨어뜨리므로 `:359` 국면게이트는 **급락이 아닌 순간에만 도달**한다. ⇒ `exclude_bear` 는 「폭락일에 켜지는 게이트」가 아니라 **「폭락이 아닌 날에만 평가되는 게이트」**다. **이 순서를 모르고 「exclude_bear 가 무용」이라 결론 내면 틀린다.**

#### (c) 잘 된 것

1. **쿨다운을 「체결됐을 때만」 무장한다**(`core/trading_context.py:518-525`). 거부된 시도가 쿨다운을 무장시키면 60초마다 재무장돼 후속 진입을 **영구히 굶는다**(2026-06-09 수정). 멱등성이 아니라 **생존성(liveness)** 을 지키는 드문 수정이고, 대부분의 트레이딩 코드가 여기서 틀린다.
2. **실전 owner 게이트를 「매수에만」 건다**(`core/trading/order_executor.py:102-115`). 소유 전략 미해석 시 **매수는 막고 매도는 안 막는다.** 「게이트는 새 위험을 만드는 쪽에만」이 **주석으로 명문화**돼 있다. 막으면 포지션이 갇히므로 이 비대칭은 **방향이 옳다**.
3. **진입 밴드가 실제로 일한다.** 09-14 `203650` 신호가 2,620 → 상한 2,699 → 실시간 2,775 → **차단**. 없었으면 +5.9% 추격 진입이었다. 눌림형 +1% / 돌파형 +3% 으로 **성격별 폭을 나눈 것**도 맞다.
4. **예약 키 표기-불변 규약**(`make_reserve_id(code, owner)` · `bot/trading_analyzer.py:244-250` · `order_executor.py:122-146`). owner 표기가 폴더키/클래스명으로 분열하는 코드베이스에서 **「인자가 아니라 슬롯 객체에서 읽는다」**를 규약으로 굳힌 것은 근본 처방이다.
5. **no-lookahead 보증이 단일 지점**(`core/trading_context.py:142-174`). `date`/`datetime` 폴백까지 있고 매수·매도가 모두 이 한 함수를 지난다. (단 ②의 가짜 분봉 경로는 이 보증 **밖**이다 — X7.)

#### (d) 구조적 약점 + 「이대로 두면 어떤 사고」

**약점 ③-1 — 「한 번만 산다」를 지키는 실효 방벽이 상태 인덱스 하나인데, 그 상태 머신이 강제되지 않는다.**
`get_selected_stocks()` 가 `stocks_by_state[SELECTED]` 만 본다는 사실이 유일한 실효 방벽이다. 앞의 가드들은 09-14 **전부 0회 발화**(중복소유 0 · 25분 쿨다운 0 · 전역 POSITIONED 재확인 0 · 중복 매수 주문 방지 0 · `[모호조회]` 0). 그런데 `change_stock_state` 는 잘못된 전이를 **경고만 하고 실행**한다.
> **사고 시나리오** — `execute_virtual_sell` 실패 → `bot/trading_analyzer.py:443-446` 이 **이미 COMPLETED 인 슬롯을 POSITIONED 로 되살린다**(전이 위반 → WARNING 만) → 유령 포지션 → 다음날 복원 대사에서 「계좌엔 없는데 장부엔 있는」 행 → 실전이면 **`LiveStartupAbort`**(기존 P2-28)로 그날 봇이 안 뜬다.

**약점 ③-2 — 페이퍼와 실전의 중복방지 「집합」이 다르다. 5개월 무사고가 실전 멱등성의 증거가 아니다.**

| 가드 | 페이퍼 라이브 경로 | 실전 경로 |
|---|---|---|
| SELECTED 인덱스 | 있음 | 있음 |
| 전역 POSITIONED 재확인 | 있음(`trading_analyzer.py:127`) | 있음 |
| 60초/3건 진입억제 | 있음 | 있음 |
| `is_buying` 플래그 | **없음** | 있음(`order_execution.py:182,216`) |
| `_active_buy_stocks` 중복주문 맵 | **없음** | 있음(`order_executor.py:117-120`) |
| `is_sell_cooldown_active` | **없음** | 있음(`order_execution.py:195`) |
| `can_add_position` | **없음** | 있음(`order_execution.py:202`) |
| owner 해석 게이트 | **없음** | 있음(`order_executor.py:110`) |
| BUY_PENDING 실체 | 마이크로초(체결 후 형식 전이) | **최대 5분** |

페이퍼는 `is_virtual_mode` 분기(`trading_analyzer.py:272`)라 `place_buy_order` 를 **아예 안 탄다**. ⇒ **실전 전환일은 한 번도 라이브에서 실행된 적 없는 5개 가드가 동시에 처음 켜지는 날**이다.
> **사고 시나리오** — `_active_buy_stocks` 는 **종목코드 단독 키**다(`order_executor.py:117`, 주석이 스스로 인정). 1전략 인스턴스면 무해하나 **2전략으로 늘리는 순간 B 전략의 정당한 매수가 A 전략의 미체결 주문 때문에 떨어진다.** 로그는 WARNING 한 줄이라 사후 추적이 안 된다.

**약점 ③-3 — 한 전략이 「왜 안 샀는가」를 로그로 구분할 수 없다.** → (e) X3. **이 검토의 최중요 발견**이다.

**약점 ③-4 — 진입 억제가 「전략별」이라 시스템 전역 한도가 없다.**
`ctx_for_strategy`(`main.py:405-416`)가 전략별 `TradingContext` 를 캐시하고 쿨다운 상태는 **인스턴스 필드**(`trading_context.py:84-86`)다. ⇒ 8전략이면 **8벌의 독립 쿨다운**. 「장 시작 동시 진입 억제」라는 이름과 달리 **시장 전체 진입 속도는 제어되지 않는다**.
> **실전 시나리오** — 갭상승 개장일에 8전략이 순차로 각 1건 발주 → 5분 내 8종목 진입 → **9% 고정 사이징이면 `real_total_funds_cap` 의 72% 를 5분에 태운다.** 09-14 는 급락게이트가 대부분 막아 11:05:11~11:10:47 사이 4건에 그쳤을 뿐이다.

**약점 ③-5 — swing 이라 EOD 시각 이후에도 매수가 열려 있다.**
`ctx.buy` 11번 가드(`:449`)는 **intraday 전략만** 차단한다. 라이브 8전략이 전부 swing 이므로 `on_tick` 은 15:00 EOD 블록 이후 **15:28:48 까지 계속 돈다**.
> **사고 시나리오** — **15:29 진입 후 다음 개장까지 장중 백스톱 없는 갭 노출.** 09-14 는 급락게이트가 막아 실현되지 않았다.

#### (e) 신규 결함

| # | 결함 | 위치 | 모드 | 검수 판정 | 심각도 |
|---|---|---|---|---|---|
| **X3** | `max_positions` 캡 포화가 **「룰 미충족」과 같은 로그** → 3전략 고도화 계측의 **분모 오염** | ma20 `strategy.py:142` · minervini `:157` · daytrading `:134` → `strategies/base.py:662-665` | 공통(계측) | **CONFIRMED** · 줄번호 검수가 재확인 | **P1** |
| **X8** | 급락/CB/국면 차단 로그에 **종목도 전략도 해석지수도 없다** → 전략별 귀속 불가 | `core/trading_context.py:355`(+`:334`, `:363`) | 공통 | **CONFIRMED** · 713줄 **전수** 동일 형태 확인 | P2 |
| **X9** | `enable_re_trading=True` **하드코딩** → 미체결 1회로 종목이 **당일 후보 풀에서 증발** | `core/trading/order_execution.py:54`, `:478-486` | **실전** | **CONFIRMED** · 그리고 **기존 P2-19 를 반증**(§3) | P2 |
| **X24** | `MAX_NEW_ENTRIES_PER_CYCLE=3` 이 **도달 불가**(쿨다운 60 > 창 15) | `config/constants.py:410,414,418` + `core/trading_context.py:479-508` | 공통 | **CONFIRMED** · `max_capital_pct` 계열 **7번째** 죽은 노브 | P3 |
| **X25** | 같은 틱에 일봉을 **두 번**, 한쪽만 미확정봉 드롭 | `strategies/base.py:614`(드롭 O) vs `bot/trading_analyzer.py:139`(`days=140`, 드롭 X) | 공통 | **CONFIRMED** · 오늘 무해(길이 게이트 전용) | P3 |
| **X26** | `TradingStock.buy_cooldown_minutes` 가 config 와 **배선돼 있지 않다** | `core/models.py:196`(기본 25) ↔ `:332`(`OrderManagementConfig` 기본 20) ↔ `:398`(JSON 은 후자로만 파싱) | 공통 | **CONFIRMED** · **JSON 을 고쳐도 25분은 안 바뀐다** | P3 |

**X3 — 왜 P1 인가 (상세)**

```
strategies/book_pullback_ma20/strategy.py:133  if timeframe != "daily": return None
                                        :137  if stock_code in self.positions: return self._check_sell(...)
                                        :140  if self.daily_trades >= self._max_daily_trades: return None
                                        :142  if len(self.positions) >= self._max_positions: return None   ← 캡
(minervini :152/:155/:157/:161 · daytrading :129/:132/:134/:138 — 순서만 다르고 구조 동일)
```
그 `None` 을 프레임워크가 받아 찍는 문구가 **`[신호없음] {code}: generate_signal None 반환 (일봉 81건)`** — **「캡이 꽉 찼다」와 「룰이 안 맞았다」가 글자 하나 다르지 않다.**
- **매매 사고가 아니라 계측 사고다.** 09-05 결정(3전략 집중)·09-11 결정(4전략)의 관측이 **전부 이 로그를 분모로** 쓴다.
- 「ma20 이 09-14 폭락일에 0건 매수」를 「룰이 안 걸렸다」로 읽으면 **정반대 결론**이 나온다 — 실제로는 **평가조차 안 했다**.
- 09-14 EOD 의 「daytrading 후보 20/20 KOSDAQ 이라 사전등록 P1·P2 판정 불가」와 **같은 계열의 두 번째 사례**다.
- **재현법(실행 금지)**: `grep -c "BookPullbackMa20Strategy.*매수검토 9종목"` ≈ 80 인데 `grep -c "매수 시그널"` = 0. 두 수만 보면 「9종목을 80번 봤는데 한 번도 안 걸렸다」로 보이지만, `[sync_positions] 5종목` + `config.yaml:35 max_positions: 5` 를 합치면 **첫 틱부터 불가능**이었다.
- **수정안(제안)**: 캡 `return None` **직전에 10분 쓰로틀 INFO 1줄** — `[캡] {code} 평가 스킵 — 보유 {len}/{max}`. 쓰로틀은 `strategies/base.py:549 _should_log_ontick` 재사용 ⇒ 하루 몇 줄. **룰 로직은 한 글자도 안 바뀌므로 6주 동결 위반이 아니다**(「계기 추가」로 사전등록 분리 권고).
- ⚠️ **대안(캡을 올린다)은 반대.** 캡은 백테스트 K 와 묶여 있다(minervini K=3 은 K=5 가 BULL 에서도 PnL 음전이라 살아남은 값 · `config.yaml:35` 주석). **문제는 캡이 아니라 캡이 보이지 않는 것이다.**
- 🔴 **검수 보강 — 이 검토가 못 한 것**: **오염이 09-14 하루만인지 미확정**이다. `logs/robotrader_template_2026090*.log`·`2026091[01].log` 로 같은 대조를 돌려 **오염 기간을 특정**해야 3전략 고도화 계측을 되살릴 수 있다. **다음 세션 1순위**(§7).

**X8 · X9 · X24~X26 — 시나리오·수정안(제안)**

- **X8** — 09-14 실측 **713줄 전부** `매수 판단 스킵: 시장급락 (KOSPI -3.45% (임계값: -2.5%))` 형태로 **종목코드 0 · 전략키 0**. 로거 이름도 전략 무관한 `trading_context`. **대조**: 같은 함수의 진입억제(`:490`,`:503`)와 밴드 거절(`trading_analyzer.py:176`)은 **종목코드를 싣는다** — 계기 품질이 가드마다 들쭉날쭉하다. **시나리오**: 「daytrading 축을 auto 로 바꾼 효과」를 판정하려면 「어느 전략의 어느 종목이 어느 지수 임계로 막혔나」가 필요한데 지금은 캐시 미스 때만 남는 107줄로 **역추정**해야 한다 — **그래서 09-14 사전등록 P1·P2 가 「판정 불가」로 끝났고, 같은 일이 매 관측일 반복된다.** **수정안**: `f"{stock_code} 매수 판단 스킵: 전략={self._strategy_key} 지수={resolved_index} {crash_reason}"` + (종목,사유) 10분 쓰로틀 재사용 ⇒ **713줄이 종목당 1줄로 줄면서 정보량은 늘어난다. 1줄 · 동작 0 변경.** 검수 평가: **「이 검수에서 비용 대비 효과가 가장 큰 한 줄」**.
- **X9** — 기전: 실전 매수는 판단 시점 현재가 지정가라 상승 중엔 잘 안 붙는다 → 300초 타임아웃 → `BUY_PENDING → COMPLETED`(`enable_re_trading=True`, config 배선 **0건**). 그런데 매수 루프는 **SELECTED 만** 순회하고 `COMPLETED → SELECTED` 복귀는 재선정 분기뿐이며 **장중 호출자 0**. ⇒ **실전 첫날, 지정가가 한 번 안 붙은 종목은 그날 다시 시도되지 않는다.** 페이퍼는 즉시 체결이라 이 경로가 **0회 실행**(09-14 `타임아웃 복구` 로그 0건). **수정안**: 값을 고르기 전에 **타임아웃 복구 로그를 WARNING 으로 올리고 경보 대상에 넣을 것.** 그 다음 `enable_re_trading` 을 config 로 빼서 **명문화**.
- **X24** — 기전이 결정적이다: 카운터는 창(15초) 경과 시 0 리셋(`:480-485`) → 한도 검사(`:487-495`) → 쿨다운 검사(`:497-508`) 순이고, **증가는 체결 성공시에만**(`:522-525`). 두 진입 사이 최소 60초 동안 창이 **최소 4회 리셋**되므로 검사 시점의 값은 **항상 0**. 3 에 도달 불가. **위험은 매매가 아니라 오독** — 실전 사이징 결재(C1)에서 「분당 진입 상한」을 이 상수로 계산하면 **틀린다**. **수정안**: 상수 주석에 「쿨다운이 창보다 길면 이 값은 무의미」 명기(동작 0 변경).
- **X25** — 후자는 `len < CANDIDATE_MIN_DAILY_DATA` 게이트에만 쓰여 오늘 무해하나 **「같은 이름의 일봉이 두 벌 있고 한쪽만 미확정봉을 포함한다」**는 배선은 언젠가 no-lookahead 를 깬다 — **(c)-5 의 단일 지점 보증이 여기서 깨진다.** 비용도 있다(DB 호출 `80 × 후보수 × 2`).
- **X26** — 지금은 두 값이 우연히 같아(25 vs 25) 무해하다. `TradingStock` 필드 대입 **0건**.

#### (f) 고수 권고 3줄

| 층 | 권고 |
|---|---|
| **지금 당장** | `core/trading_context.py:355`(+`:334`,`:363`)에 **종목코드·전략키·해석된 지수**를 싣고 (종목,사유) 10분 쓰로틀을 건다(X8). **1줄 · 동작 0 변경** · 713줄이 종목당 1줄로 줄면서 09-14 사전등록 P1·P2 의 「판정 불가」가 **다음 관측일부터 해소**된다. **같은 패스에 X3 의 캡 로그 1줄**을 넣으면 3전략 고도화 계측의 분모가 그날부터 정직해진다. |
| **실전 전환 전** | `order_execution.py:54 enable_re_trading` 의 값을 **결정하고 명문화**(X9). 「미체결 → 조용한 매수 0건」과 「미체결 → 재발주 폭주」는 **서로 다른 사고**이고 검수 결과 **전자가 옳다**(§3). 어느 쪽이든 **타임아웃 복구 로그는 WARNING + 경보**로 올릴 것. |
| **장기** | 「한 번만」을 **상태 인덱스의 부작용에 기대는 구조**를 끝낸다 — `change_stock_state` 를 **전이 강제(위반 시 예외)** 로 바꾸고 매수 멱등키를 `(거래일, 종목, owner)` 로 명시. 지금은 가드 14겹 중 13겹이 09-14 에 **한 번도 발화하지 않았고**(무해해서가 아니라 앞단이 다 막아서), 그 13겹이 실제로 동작하는지 **아무도 모른다**. |

---

### ④ 매도 진입

#### (a) 실제 흐름 사슬 — 한 포지션에 판단 주체가 **최대 4개**

```
[A] 프레임워크 백스톱   main.py:460 (매 라운드 = 실측 12.2초, «전» 포지션)
  core/trading/position_monitor.py:120 check_positions_once
    :127 _monitor_stock_states  → :131 check_order_completions  :134 _update_position_prices
    :137 _check_positioned_stocks_for_sell → :193 _analyze_sell_for_stock
          :206 current_price = _get_current_price()   (온디맨드 API → 캐시(항상 None) → collector)
          :219-224 is_before_rebalancing = (hour==9 and minute<5)   ← ★ 유예 조건
          :227 장기보유 익절   :239 장기보유 손절(유예 O)
          :253 strategy_for_sell = trading_stock.owner_strategy or self._strategy   ← ★ 오귀속 지점
          :254 max_holding_days   :292 공통 트레일링(strategy_for_sell is None 일 때만)
          :314 목표 익절   :326 손절(유예 O)  ← 09-14 손절 7건 전부 여기
          :339 [C] 전략 매도 시그널 — «intraday» 로 가짜 분봉 전달
          :411 _execute_sell → execute_virtual_sell / execute_real_sell
    :140 _check_pending_sell_retries

[B] 전략 룰(일봉)     main.py:486 on_tick → strategies/base.py:691-713
  :691 for stock in ctx.get_positions()      ← ★ owner 필터 «없음»(전 포지션)
  :694 exit_timeframe == "daily" → ctx.get_daily_data()   :701 generate_signal(timeframe="daily")
  :709 ctx.sell(code, reason, signal) → core/trading_context.py:538-605(소유권·is_selling·하한가 가드)
       :600 trading_analyzer.analyze_sell_decision → :385-393 signal 전달 시 «재판단 생략»
       :431 move_to_sell_candidate → :436 execute_virtual_sell / :455 execute_real_sell

[C] 전략 룰(분봉)     position_monitor.py:339-366   ← [A] 안에 «숨어 있는» 두 번째 전략 호출
[D] EOD              main.py:504 → bot/liquidation_handler.py:157 / :233
  :177-183 / :263-270  owner = getattr(ts,'owner_strategy',None)
                       strategy_for_eod = owner or getattr(decision_engine,'strategy',None)
                       if strategy_for_eod and not should_liquidate_eod(code): continue
```

**[A] 내부 우선순위** (위에서부터 먼저 이김, 각 분기가 `await _execute_sell; return` 이라 **한 틱에 하나만** 발화):
`stale 익절` > `stale 손절` > `max_holding_days` > `트레일링(비전략 포지션만)` > `목표 익절` > `손절` > `전략 분봉 시그널`

**[A] 와 [B] 사이에는 «우선순위가 없다».** 서로 다른 루프다 — [A]는 **12.2초마다 전 포지션**, [B]는 **약 290초마다 1전략**. 09-14 실측 비율 **[A] 8건 : [B] 1건**.
🔴 게다가 **상태 궤적이 두 가지**다:
- [A] 페이퍼: `position_monitor.py:451` 이 `execute_virtual_sell` 을 **직접** → `POSITIONED → COMPLETED` (실측 `388050 positioned -> completed`)
- [B] 페이퍼: `trading_analyzer.py:431` 이 `move_to_sell_candidate` **먼저** → `POSITIONED → SELL_CANDIDATE → COMPLETED` (실측 `204840 sell_candidate -> completed`)

SELL_CANDIDATE 를 **전제로 요구하는** 후처리(실전 `execute_real_sell:761`)가 [A] 경로에선 **없다**.

**3전략 청산 룰 — 어떤 봉·어떤 가격으로**

| 항목 | `book_pullback_ma20` | `minervini_volume_dryup` | `daytrading_3methods_breakout` |
|---|---|---|---|
| 손절 / 판정 주체 | −8% / **[A]** | −8% / **[A]** | −10% / **[A]** |
| 손절 평가 | **실시간 현재가** vs `position.avg_price` | 동일 | 동일 |
| 익절 / 판정 주체 | +10% / **[A]** | +12% / **[A]** | +10% / **[A]** |
| max_hold | 50거래일 | 20거래일 | 10거래일 |
| max_hold 판정 주체 | **[A] «와» [B] 둘 다** | 동일 | 동일 |
| MA trailing | MA20 하향 이탈, **수익 중에만** · **[B] 전략 룰만** · **D-1 확정 종가** | 없음 | 없음(`trail_ma: null`) |
| 공통 트레일링(+5%/−3%) | **적용 안 됨**(전략 포지션이므로) | 동일 | 동일 |
| [C] 분봉 `_check_sell` 도달 | **불가**(`:133` 가드가 positions 분기 «앞») | **가능**(`:161` 뒤) | **가능**(`:138` 뒤) |

🔑 **핵심 비대칭**: sl/tp 는 **라이브 현재가**(12초 해상도), MA trailing·max_hold 는 **D-1 확정 종가**(하루 1값). **두 시계가 한 포지션 위에서 동시에 돈다.** 2026-08-25 결정(「sl/tp 를 D-1 종가로 판정하면 갭 체결 시 환영 익절」)의 결과이고 **방향은 옳다**.

🔴 **max_hold 가 세 곳에서 «다른 정의»로 평가된다** — [A] `days_held` → VTM `get_days_held` → `count_trading_days_between(last_buy_time, now)`(−1 **없음**) / [B] ma20·daytrading `count_trading_days_between(entry_time, now) − 1` / [B] minervini `entry_time + 1일` 부터 카운트. ⇒ **셋이 하루씩 어긋날 수 있고 [A] 가 하루 먼저 발화한다.** 09-14 발화 0건이라 관측되지 않았다.

**「매수·매도 룰 동시 참」(08-24 결함 17/71)이 3전략에 있는가 — 없다. 구조적으로 불가능하다.** 세 전략 모두 `generate_signal` 이 **단일 if 분기**(`if code in self.positions: return self._check_sell(...)` … `return self._check_buy(...)`)라 한 호출이 BUY 와 SELL 을 **동시에 낼 수 없다**. rs_leader 결함은 두 룰을 **병렬 평가**하기 때문이고 3전략은 그 구조가 아니다.
다만 **잔여 채널 2개**: ①`ctx.get_positions()`(`trading_context.py:300-307`)에 **owner 필터가 없다** — `get_selected_stocks` 에는 있는데 여기엔 없다 ⇒ 모든 전략이 **전 포지션 33~37개**를 매도 평가하고, 남의 포지션은 `self.positions` 에 없으니 **`_check_buy` 로 떨어져 BUY 신호가 나올 수 있으나 `base.py:702` 가 SELL 만 받아 조용히 버려진다.** ②[C] 분봉 경로가 2전략에 열려 있다(→ X7).

#### (b) 09-14 실측 대조 — 매도 9건 전수

| # | 시각 | 종목 | 사유 | **판단 주체** | 소유 전략 | 체결가 / 손익 |
|---|---|---|---|---|---|---|
| 1 | 09:04:48 | 204840 | `MA20 이탈 (종가 4680 < MA 4704)` | **[B] 전략 룰(일봉)** | rs_leader | 4,510 / −41,400 |
| 2 | 09:05:10 | 388050 | `손절 실행 (-3.91% <= -3.00%)` | **[A] 백스톱** | ma5 | 10,810 / −61,600 |
| 3 | 09:05:11 | 289080 | `손절 실행 (-3.02% <= -3.00%)` | **[A] 백스톱** | ma5 | 2,565 / −46,960 |
| 4 | 09:05:12 | 079650 | `손절 실행 (-10.70% <= -8.00%)` | **[A] 백스톱** | rs_leader | 6,930 / −72,210 |
| 5 | 10:15:31 | 002780 | `손절 실행 (-8.11% <= -8.00%)` | **[A] 백스톱** | rs_leader | 6,910 / −56,730 |
| 6 | 12:07:54 | 069540 | `목표 익절 도달 (15.43% >= 15.00%)` | **[A] 백스톱** | rs_leader | +101,745 |
| 7 | 12:46:42 | 001210 | `손절 실행 (-8.15% <= -8.00%)` | **[A] 백스톱** | rs_leader | 11,390 / −56,560 |
| 8 | 14:00:25 | 005935 | `손절 실행 (-8.01% <= -8.00%)` | **[A] 백스톱** | elder | 184,900 / −32,200 |
| 9 | 14:43:34 | 452190 | `손절 실행 (-3.03% <= -3.00%)` | **[A] 백스톱** | ma5 | 4,965 / −47,895 |

- **손절 7/7 = 전부 프레임워크 백스톱.** 전략 룰 발 매도는 **1/9**. **고도화 3전략(ma20·minervini·daytrading)의 매도는 0건.**
- 손절률 −3.0% 3건 = ma5 config · −8.0% 3건 = rs_leader/elder config · 익절 +15.0% 도 config 유래 ⇒ **전부 정상 배선**(복원 로그가 `DB 복원: … (익절:15.0% 손절:3.0%)` 로 값을 싣는다).
- **손절 3건이 09:05:10 · 09:05:11 · 09:05:12 에 몰렸다**(전체 손절의 **43%**). 09:05:00 유예 해제 직후 보유 33~36종목이 **한 패스**에 평가된 결과다. 그리고 `09:04:48 204840 전략 매도신호` 는 **유예 창 «안»에서 통과했다**(전략신호는 유예 미적용).
- **[A]는 임계를 «넘긴 뒤»에야 판단한다** — `079650` 은 `-10.70% <= -8.00%` 로 **임계보다 2.70%p 더 깊은 곳**에서 체결. 나머지도 −8.11 / −8.15 / −8.01 / −3.03 / −3.02 / −3.91 로 **전부 임계 초과 지점**이다(밤새 갭이라 임계와 체결 사이에 호가가 없다).
- **[B] 판정가 vs 체결가 괴리**: `204840` 판정 근거 종가 **4,680** vs 실제 체결가 **4,510** = **−3.6%**. 그리고 같은 거래를 전략 콜백은 `-6.2%`, VTM 은 `-41,400원` 으로 보고한다 — **세 숫자의 기준이 서로 다르다.**
- **[D] EOD** 15:00:02 보유 **33/33 전량** `EOD 청산 스킵 (전략 … 거부)` → `15:00 시장가 일괄매도 요청 완료`. 8전략 전부 swing 이라 EOD 는 **사실상 no-op**. ⇒ `owner_strategy` 인스턴스가 **33/33 해석됐다**.
- **경쟁 계기 0** — `매도 실패` 0 · `POSITIONED로 복원` 0 · `Circuit Breaker` 0 · `이미 매도 진행 중` 0 · `[모호조회]` 0. ⇒ **경쟁 조건은 오늘 한 번도 시험받지 않았다.** 「사고가 없었다」는 「방벽이 동작한다」의 증거가 아니다.

#### (c) 잘 된 것

1. **sl/tp 를 라이브 현재가로, MA·max_hold 를 확정 일봉으로 「나눈」 것**(`position_monitor.py:314-335` + 3전략 `strategy.py:231-232` 주석). 갭 체결 시 D-1 종가로 익절을 날조하던 **환영 익절**을 제거했고, **세 전략 파일이 모두 같은 주석으로 규약을 명시**한다. 드물게 잘 된 「경계 합의」다.
2. **공통 트레일링(+5%/−3%)을 전략 포지션에서 「뺐다」**(`position_monitor.py:288-293`). 「전략별 손익비가 governing」이라는 2026-06-24 결정이 정확히 반영됐고 비전략(레거시) 포지션엔 안전망으로 남겼다. **「예외를 없앤 것」이 아니라 「적용 범위를 좁힌 것」**이라 회귀가 없다.
3. **`is_selling` 해제 지점이 전 경로에 깔려 있다**(`position_monitor.py:456,463,478,496,505` + `order_execution.py:394,407,503,584` + `order_completion_handler.py:322,361,462`). 해제 누락으로 **포지션이 갇히는 사고**를 방어적으로 막았다(중복 해제는 무해).
4. **매도 소유권 가드가 「폴더키 또는 클래스명 둘 중 하나만 맞으면」 통과한다**(`trading_context.py:568-575`). owner 표기 분열(2026-07-23 실증)에서 **정당한 매도를 오거부하지 않는** 쪽으로 설계됐다. **매수 가드는 반대로 엄격하다 — 이 비대칭이 정확하다.**
5. **매도에는 하한가 차단이 없고 「경고만」 한다**(`trading_context.py:593-597`). **손절이 필요한 자리에서 가격 가드가 탈출을 막지 않는다.**
6. 🆕 **검수가 3편 모두 놓쳤다고 지적한 것** — `bot/state_restorer.py:1044-1085` 의 **고아 레그 3분류**(미선언 라벨 = abort / 선언됐으나 미로드 = 격리 / 무기명 = 격리)는 이 코드베이스에서 드물게 **「모른다」를 「안전」으로 접지 않은** 자리다. 분류마다 **사람이 할 조치까지 메시지에 적었다**("config 를 고쳐라" / "실거래 테이블 strategy 를 UPDATE 해라"). 격리 메시지는 「전략 고유 청산 없이 프레임워크 백스톱(position_monitor tp/sl · EOD 일괄청산)만 적용된다」고 **명시**한다 — **설계자가 이 상태를 알고 문서화했다.**

#### (d) 구조적 약점 + 「이대로 두면 어떤 사고」

**약점 ④-1 — 매도 판단 주체가 4개인데 「조정자」가 없다.**
[A]는 12.2초·전 포지션, [B]는 약 290초·전략별, [C]는 [A] 안에 숨어 있고, [D]는 15:00 1회. 서로의 존재를 모르고 `is_selling` **하나**로 조율한다. 09-14 충돌 0회인 것은 **[B]가 1건밖에 안 나왔기 때문**이지 설계가 막아서가 아니다.
> **사고 시나리오** — **[B] 페이퍼 경로는 `is_selling` 을 «세우지» 않는다**(grep: `bot/trading_analyzer.py` 에 `:441` 의 **해제** 대입만 있고 **설정** 대입이 없다). [B]가 `move_to_sell_candidate → execute_virtual_sell` 을 도는 동안 [A]가 같은 포지션을 집어 `is_selling=True` 로 놓고 `execute_virtual_sell` 을 **두 번째로** 호출한다. **VTM 의 `buy_record_id` 멱등성(DB 부분 유니크 인덱스)에 기대고 있을 뿐 상위 레이어에 방벽이 없다.** 실전 표에는 그 멱등키조차 **없다**(→ X2).

**약점 ④-2 — 매도 「성공」의 의미가 [A]와 [B]에서 다르다.**
[A] 실전: `position_monitor.py:470-473` 의 `success` = `execute_real_sell` = **주문 접수**(체결 아님)인데 `_record_sell_success` 가 실패 카운터를 **리셋**한다(`:610-616`).
> **사고 시나리오** — **접수만 되고 체결이 안 되는 종목은 Circuit Breaker 가 영원히 안 켜진다.** (기존 P2-13 과 뿌리는 같지만 결과가 다르다 — 「CB 무력화」.)

**약점 ④-3 — 장중 방어선이 사실상 [A] 백스톱 하나이고, 그 백스톱은 갭을 못 막는다.**
3전략의 전략 룰 청산은 **D-1 종가 기준이라 장중에 값이 변하지 않는다**. 실질 장중 방어선은 [A]의 `stop_loss_rate` 하나이고, [A]는 **현재가가 이미 임계를 넘은 뒤**에야 판단한다(위 실측 7건 전부). 게다가 [B]의 평가 주기가 **약 290초**라 검수 정정은 **이 결론을 강화한다** — 전략 룰 매도가 더 드물게 평가된다 = **백스톱 의존도가 더 높다**.
> **사고 시나리오** — 실전 시장가 매도(`price=0`)라 **임계 초과분이 그대로 슬리피지로 실현**된다. 그리고 09:00~09:05 유예가 **손절만** 막으므로, 유예는 갭을 **막은 게 아니라 늦춘 것**이다(09-14 실증 43%).
> ⚠️ **그 비용을 측정할 수 없다** — 09:00~09:05 구간 가격 계기가 없다. 측정하려면 스킵 시 「스킵 안 했으면 얼마였는지」를 INFO 로 남기는 **shadow 계기**가 필요하다(사전등록 대상).

**약점 ④-4 — `strategy_for_sell` 폴백이 「남의 전략 룰로 청산」을 만든다.**
`position_monitor.py:253` `strategy_for_sell = trading_stock.owner_strategy or self._strategy`. 인스턴스가 None 이면 **`self._strategy`(단일 고정, 보통 첫 전략)** 로 폴백 ⇒ **남의 전략 max_hold·매도룰로 청산**될 수 있다.
> 🔑 **검수 재배치** — 이것은 fail-open 이 아니라 **오귀속**이고, EOD 가 아니라 **매 12초 루프**에서 돈다. ~~B-10(EOD fail-open)~~ 에 붙어 있던 등급을 **이쪽(X16)으로 옮겨야 한다.** 09-14 는 복원이 33/33 해석에 성공해 안 터졌다.

#### (e) 신규 결함

| # | 결함 | 위치 | 모드 | 검수 판정 | 심각도 |
|---|---|---|---|---|---|
| **X7** | [C] 분봉 whipsaw 가드가 **3파일에서 위치가 달라** minervini·daytrading 은 무방비 | ma20 `:133`(앞) vs minervini `:161`·daytrading `:138`(뒤) + `position_monitor.py:359` | 공통 | **CONFIRMED** · ②의 A-N8 과 **병합(M2)** | P2 |
| **X10** | `daily_trades` 가 **매도까지 센다** + 리셋 경로 없음 → 전략 **영구 매수불능** | ma20 `:147-148` · minervini `:166-167` · daytrading `:143-144` (+ 게이트 `:140`) | 공통 | **CONFIRMED** · 그러나 ~~원인 = `_candidates_loaded`(P2-25)~~ **틀렸다** → 원인은 **CR-1**(§3) | P2 |
| **X11** | 매도 실패 복원이 **COMPLETED 슬롯을 POSITIONED 로 되살릴 수 있다**(두 복원 경로 조건 비대칭) | `bot/trading_analyzer.py:439-447`(**조건 없음**) vs `core/trading_decision_engine.py:797-799`(**조건 있음**) | 공통 | **CONFIRMED** · 도달성은 추정(09-14 발화 0) | P2 |
| **X16** | `strategy_for_sell = owner or self._strategy` → **남의 전략 룰로 청산**(매 12초 루프) | `core/trading/position_monitor.py:253`, `:339` | 공통 | **CONFIRMED** · **B-10 의 등급을 이리로 이전** | P2 |
| **X27** | ~~EOD 청산 가드 fail-open → 「첫날 15:00 시장가 전량 청산」~~ | `bot/liquidation_handler.py:177-183`, `:263-270` | 공통 | 위치 CONFIRMED / **시나리오 REFUTED** → **P3 강등**(§3) | ~~실전 P2~~ → P3 |
| **X17** | `on_market_open()`/`on_market_close()` 가 **8전략 중 1개에만 간다** | `main.py:246-254`, `:256-264`, `:238-242`(`next(iter(...))`), 호출 `:440` | 페이퍼(실전 무해) | **CR-1 · 검수자 신규 · 로그로 증명** | P2 |

**시나리오·재현법·수정안(제안)**

- **X7** — ma20 주석이 위험을 **명시**한다: *「position_monitor 는 보유종목 매도판단에 무조건 timeframe=intraday 로 분봉을 전달한다. trail_ma 청산을 분봉 MA20 으로 평가하면 매수 직후 whipsaw 청산이 발생하므로 분봉 경로를 여기서 차단한다」*(`:129-132`). **그 위험 인식이 ma20 파일에만 반영됐다.** 현재 무해한 이유는 두 전략의 `evaluate_sell_conditions` 가 `df` 를 지표로 안 쓰기 때문(daytrading `trail_ma=null`). **시나리오**: 고도화 중 daytrading 에 trailing 을 넣거나 minervini 에 `trend_flip` 을 넣는 순간(둘 다 백테스트 variant 에 존재) **분봉으로 평가되어 진입 당일 청산** — 그게 정확히 2026-06-09 Elder `192080` 사고다. 백테스트와 라이브가 갈리는데 **원인이 전략 파일이 아니라 `position_monitor.py:359` 에 있어 찾기 어렵다**. **수정안(검수 권고)**: ~~두 전략 파일의 가드를 3줄 이동~~(룰 파일 수정 = 동결 대상) 대신 **`position_monitor.py:341` 에 `exit_timeframe` 조건 1줄**.
- **X10** — 코드가 명확하다: `def on_order_filled(self, order): self.daily_trades += 1` 이 **`if order.is_buy:` 분기 «이전»**이다. **09-14 직접 증거**: Elder 는 당일 **매수 0 · 매도 1**(005935 손절)인데 `15:00:02 장 마감 — 거래 1건, 보유 9종목` ⇒ **매도가 `daily_trades` 를 올렸다.** ⇒ **손절 3건이 나면 그날 남은 진입 예산은 5가 아니라 2다.** 폭락일처럼 손절이 몰리는 날에 **진입 예산이 가장 먼저 마른다** — 백테스트에 없는 라이브 전용 제약이다. **연쇄**: `daily_trades` 는 `on_market_open()` 에서만 0 이 되는데 🔴**그 콜백이 8전략 중 1개에만 간다**(X17) ⇒ **`_candidates_loaded` 를 되살려도 7전략은 리셋되지 않는다. 결론은 옳고 실제로는 더 나쁘다.** **수정 경로 정정**: ~~① `daily_trades += 1` 을 `is_buy` 안으로~~(룰 파일 수정 = 동결 대상)보다 **③ 일자 변경 감지 리셋 + X17 콜백 전수화**가 근본이고 **동결과 무관**하다.
- **X11** — `sell_ok=False` 의 원인에 **「이미 팔려서 열린 매수기록이 없다」가 섞여 있다**(`trading_decision_engine.py:855-863` → `:944 return False`). 그 경우 슬롯은 이미 COMPLETED 인데 `bot/trading_analyzer.py:443` 이 **POSITIONED 로 되돌린다**. **도달 경로**: [A]와 [B]가 같은 포지션에 연달아 발화하고 [A]가 먼저 성공 → `is_selling` 이 [A] 성공 직후 풀리므로 [B]의 `trading_context.py:578` 가드는 **통과한다**. **시나리오**: 유령 POSITIONED → 다음 사이클 [A] 재시도 → 실패 → 3회 → CB 30분 → EOD 강제완료 CRITICAL. 페이퍼는 장부 오염으로 끝나지만 **실전은 실계좌 대사 실패 → 다음날 `LiveStartupAbort`**(기존 P2-28·29 의 상류). **수정안**: `:443` 복원 전에 `if state in (SELL_CANDIDATE, SELL_PENDING)` **1줄** — 실전 경로(`_restore_to_positioned:797-799`)가 **이미 그렇게 하고 있다**. **두 복원 경로의 조건이 다른 것 자체가 결함**이다.
- **X16** — **수정안**: `position_monitor.py:253`(및 `:339`)의 `self._strategy` 폴백을 **「미해석이면 백스톱 전용, 전략 매도신호는 스킵」**으로. **동작 변경이므로 결재 필요.**
- **X17 (CR-1 · 검수자 신규)** — `main.py:246-254`/`:256-264` 가 둘 다 **`self.strategy`(단수)** 에만 콜백하고, `:238-242` 가 `self.strategy = next(iter(self.strategies.values()))` = **dict 첫 전략 = config 첫 항목 = `elder_ema_pullback`**. 호출 지점은 `main.py:440` 하나(`if not self._candidates_loaded:` 안). **로그가 그대로 증명**: 09-14 전체에서 `장 마감 — 거래` 가 **단 1줄**, `strategy.ElderEmaPullbackStrategy`. **대조**: `on_init` 은 `main.py:218-220` 에서 **전 전략 루프** ⇒ 그래서 daily_trades 가 기동 시엔 전부 0 ⇒ **매일 07:40 재기동이 이 결함을 가려 왔다.** **귀결 3가지**: ①X10 의 원인 귀속 정정(P2-25 를 고쳐도 절반만 닫힌다) ②전략이 `on_market_open/close` 에 의존하는 **어떤 상태도 7/8 전략에서 죽어 있다** — 고도화 중 「장 시작에 뭘 초기화한다」를 넣는 순간 **7전략에서 조용히 안 돈다** ③**실전 1계좌1전략에서는 무해**(self.strategy = 그 하나) ⇒ 실전 전환 전 필수는 아니고 **페이퍼 계측 신뢰성 문제**다(X3 와 같은 계열). **수정안**: 두 함수를 `for strat in self.strategies.values():` 루프로(각각 try). 동작 변경 = 「7전략이 콜백을 받기 시작한다」 ⇒ daily_trades 가 매일 0 으로 리셋되므로 **X10 을 룰 파일 수정 없이 닫는다**. **관측치가 바뀌므로 사전등록 대상.**
- **중복 참조** — 기존 **P2-13**(매도 성공 = 접수 + 실패 카운터 조기 리셋) **여전함**, 이 단계에서는 **CB 무력화**로 나타난다. 기존 **P3-38**(부분체결 타임아웃 owner 누락)은 **더 넓다** — `core/orders/order_timeout.py:360,395,411,423,434` 의 **모든** 타임아웃 통보가 `handle_order_timeout(order)` 를 **strategy 인자 없이** 부른다 ⇒ 다중소유 종목에서 `[모호조회]` 후 첫 소유자 슬롯을 집는다. 기존 **08-13 D2**(`ctx.sell(signal)` 신뢰 경로) **여전히 유효** — `rebalancing_mode=true` 라 재판단 경로가 영구 차단되어 **signal 전달이 [B]의 유일한 매도 경로**다. 기존 **08-24 매수·매도 동시 참** 은 **3전략에 없다**(rs_leader 고유).

#### (f) 고수 권고 3줄

| 층 | 권고 |
|---|---|
| **지금 당장** | `core/trading/position_monitor.py:341` 에 `exit_timeframe` 조건 **1줄**(X7 — ②와 공유) + `bot/trading_analyzer.py:443` 복원을 `_restore_to_positioned` 와 **같은 상태 조건**으로 맞춘다(X11, 1줄). 둘 다 **동작 변경 0**. |
| **실전 전환 전** | ~~`liquidation_handler.py:180,267` 의 극성을 뒤집는다(B-10)~~ → **이 층에서 뺀다**(§3 · 1전략 실전에서 도달 불가). 대신 **`position_monitor.py:253` 의 `self._strategy` 폴백**(X16)을 「미해석이면 백스톱 전용」으로 좁힌다 — 진짜 위험은 EOD 1회가 아니라 **매 12초 루프의 오귀속**이다. **동작 변경 → 결재.** |
| **장기** | 매도 판단을 **하나의 결정자**로 모은다 — [A]를 「신호 생성기」로 바꿔 `ctx.sell` 과 **같은 단일 실행 경로**(소유권 가드 → `is_selling` → SELL_CANDIDATE → 실행)를 타게 하면 **상태 궤적 2종·성공 정의 2종·복원 조건 2종이 한 벌로** 줄어든다. 지금은 **「어느 경로로 팔렸는가」에 따라 장부 궤적이 달라지고, 그 차이가 다음날 복원 대사의 입력**이 된다. |

---

### ⑤ 주문 체결 (발주 → 체결 → DB → 콜백 → 자금)

#### (a) 실제 흐름 사슬

**🔴 문서가 말하는 흐름부터 틀렸다.** `CLAUDE.md` 「데이터 흐름」은 `ctx.buy() → TradingDecisionEngine → OrderManager 주문 실행 → 체결 모니터링 → on_order_filled → DB + 텔레그램` 이라고 적혀 있다. **페이퍼는 `OrderManager` 를 통째로 우회한다.**

```
[실제 페이퍼 매수 사슬]
core/trading_context.py:514 ctx.buy → TradingAnalyzer.analyze_buy_decision(strategy_name=폴더키)
 ├ bot/trading_analyzer.py:253  fund_manager.reserve_funds(make_reserve_id(code,owner), gross)   [무로그]
 ├ :275  decision_engine.execute_virtual_buy
 │   └ core/trading_decision_engine.py:685 → core/virtual_trading_manager.py:669 db.save_virtual_buy → INSERT (rid)  ★DB 우선
 │      :683-693 _strategy_balances −= gross×(1+c) · _strategy_invested += · _position_owner[(code,rid)] = 폴더키
 │      :701     _buy_times[(code,rid)] = now
 │   ├ :694-697 set_virtual_buy_info(rid) · set_position · tp/sl 기입
 │   └ :703     _notify_strategy_order_filled(side="buy", order_id="VIRT-BUY-{rid}")
 ├ :317  fund_manager.confirm_order(_reserve_id, gross)   [무로그]
 ├ :322  fund_manager.add_position(code, owner)           [무로그]
 └ :337-342 _change_stock_state SELECTED→BUY_PENDING→POSITIONED
            (core/trading_context.py:529 가 직후 슬롯 owner 를 «클래스명»으로 덮어씀)

[실제 페이퍼 매도 사슬]  (진입점 3개: position_monitor.py:451 / trading_analyzer.py:436 / liquidation_handler.py:202,289,408)
 core/trading_decision_engine.py:888 → core/virtual_trading_manager.py:720 execute_virtual_sell
 ① :745-761 «메모리 원장 먼저» (owner 정규화 → cash += net · invested −= net · owner pop · 집계 동기화)  ★메모리 우선
 ② :774     db.save_virtual_sell  (실패해도 True 반환 · :804 pending queue)
 ├ :895-896 clear_virtual_buy_info / clear_position   ├ :901 _change_stock_state → COMPLETED
 ├ :919-926 fund_manager.release_investment(원가) · adjust_pnl(net) · remove_position · set_sell_cooldown
 └ :935     _notify_strategy_order_filled(side="sell")

[실전 사슬]  core/trading/order_execution.py:234 place_buy_order (유일 호출자, 상위는 execute_real_buy 뿐)
 → 메모리 pending_orders(order_base.py:32) → 브로커 폴링(framework/broker.py:793) → order_db_handler.py:117 _save_real_trade_to_db
```

**문서 ↔ 코드 괴리 3건**

| # | 문서 | 코드의 실제 | 실측 근거 |
|---|---|---|---|
| D-⑤1 | 「OrderManager 가 주문 실행 → 체결 모니터링 → on_order_filled」 | 페이퍼는 `OrderManager` 를 **한 번도 부르지 않는다** | 09-14 전수: `매수 주문 시도` 0 · `주문 완전 체결` 0 · `체결 콜백 수신` 0 · `주문 모니터링` 0 · 대시보드 `미체결 주문: 0건` ×20 · `타임아웃 복구` 0 |
| D-⑤2 | 주석이 말하는 「가상매매 = 즉시 FILLED」 경로(`order_executor.py:150,168`) | 그 경로는 `strategy="리밸런싱"`, `reason="퀀트 포트폴리오"` 로 저장한다(`:652-653`) ⇒ **리밸런싱 전용 죽은 경로** | `SELECT strategy, action, count(*) FROM virtual_trading_records GROUP BY 1,2` → **폴더키 8종만**, 그런 행 0건 |
| D-⑤3 | 「체결 → DB 저장 + 텔레그램」 순 | **페이퍼 매수는 DB → 메모리, 페이퍼 매도는 메모리 → DB.** 내구성 방향이 매수/매도에서 **정반대** | `virtual_trading_manager.py:669→683` vs `:745→774` |

**「주문 원장」의 SSOT**

- **페이퍼**: **주문 원장이 존재하지 않는다.** `pending_orders`/`completed_orders`/`order_timeouts`/`_active_buy_stocks` 전부 빈 채로 세션을 마친다. 「체결됐다」의 유일한 진실원은 **`virtual_trading_records` 행의 존재**이고 그 행을 쓰는 주체가 곧 판정자(VTM)다 — **자기 선언이며 대사 상대가 없다.**
- **실전**: 3층이 공존하는데 **우선순위가 명문화돼 있지 않다.** ①메모리 `pending_orders` = 「우리가 낸 주문」 ②브로커 = 「체결됐는가」(`framework/broker.py:793` — 정정취소가능목록 / 당일체결목록 / 둘 다 없음 = `status_unknown`) ③DB `real_trading_<id>` = 「기록」이지만 **파생물**이고 **쓰기 실패가 삼켜진다**(`order_db_handler.py:141-142`).
> **설계 판정**: ②가 ①·③을 지배해야 하는데, `status_unknown`(기존 P1-6)에서는 **②가 침묵하고 ①이 독단한다.** **「브로커가 모른다고 말할 때 누가 결정하는가」에 답이 없는 것**이 이 설계의 구멍이다.

**「정확히 한 번」의 보장 층**

| 층 | 가드 | 커버 | 구멍 |
|---|---|---|---|
| DB | `idx_virtual_trading_unique_sell`(페이퍼 매도) | 매수행당 매도 1건 | **매수엔 아무 키도 없다. 실전 표엔 매도에도 없다** |
| 슬롯 | `trading_stock.order_processed`(`models.py:182`) + POSITIONED 조기 return | 푸시 콜백 재진입 | 리셋 지점이 **4곳 + 복원 경로 2곳**으로 흩어짐 |
| 이중 경로 | 푸시 `on_order_filled` ↔ 폴링 `check_order_completions` | 매수는 POSITIONED 로 차단 | **폴링 경로는 `order_processed` 를 «세우지도 읽지도» 않는다** |
| 원장 | VTM `_pop_position_owner` | 같은 슬롯 재매도 | owner 미해석 시 `else` 로 빠짐(→ X14) |
| 자금 | `confirm_order` 는 미예약이면 경고 후 return(`fund_manager.py:365-367`) | 이중 확정 | 🔴 **쌍이 되는 `reverse_confirm`(`:388-395`)에는 아무 조건도 없다**(→ X1) |

> **결론: 「정확히 한 번」이 DB 제약으로 보장되는 것은 «페이퍼 매도» 하나뿐이다.** 나머지는 메모리 플래그 + 상태 비교이고, 그 플래그는 프로세스 재시작에 소멸한다. **실전 전환은 「유일하게 강한 보장을 갖는 경로를 끄고, 보장이 0인 경로를 켜는 일」이다.**

#### (b) 09-14 실측 대조

| 항목 | 로그 | DB | 판정 |
|---|---|---|---|
| `가상 매수 완료 처리` | **6** | `virtual_trading_records` BUY **6** | ✅ 보고값 매수 6 |
| `가상매도:`(총 매도) | **9** | SELL **9** | ✅ 보고값 매도 9 |
| ⚠️ `가상 매도 완료 처리` | **1** | SELL 9 | **불일치가 아니다** — 이 로그는 `trading_analyzer.py:449`(= `ctx.sell` 전략신호 경로) **전용**이고 손익절·EOD 경로엔 **대응 로그가 없다**. ⑤의 「체결 처리 완료」를 세는 **단일 카운터가 로그에 존재하지 않는다** |
| 매도 경로 분해 | 손절 7 + 전략신호 1 + 익절 1 = **9** | 9 | ✅ |
| 전략별 BUY/SELL | — | ma5 2/3 · rs_leader 2/5 · daytrading 1/0 · envelope 1/0 · elder 0/1 | 합 **6/9** ✅ |
| 실전 경로 | `미체결 주문` **0건** ×20 · `주문 완전 체결`/`체결 콜백 수신`/`주문 모니터링` **0/0/0** | — | **⑤ 실전 경로 완전 미가동** |
| EOD 정합성 | `total=64,392,301 = available 23,330,166 + reserved 0 + invested 41,062,135` | — | ✅ 통과 |
| FM 로그 편향 | `core.fund_manager` INFO 는 **매도 때만**(`투자 회수` 9 · `매매 손익 반영` 9 · `일일 손실 누적` 9) | — | **매수 6건은 FM 에 정상 반영됐는데 로그상 흔적 0** |
| **FM vs VTM 현금 격차** | FM available **23,330,166**(15:35:03) | `paper_trading_state` **23,330,261.64** | **95.64원** — 산식으로 정확히 재현(아래) |

**96원 검산 (전부 재현 가능 · 검수가 「3편 중 가장 정밀한 작업」으로 평가)**

```
당일 신규 매수 후 미청산 5건 gross 합 = 6,281,330 × 0.00015 =   942.2원   (VTM 이 FM 보다 «낮은» 쪽)
전일 이전 매수분 매도 8건의 매수원가 합 = 6,921,480 × 0.00015 = 1,038.2원   (VTM 이 FM 보다 «높은» 쪽)
   (452190 은 당일 왕복이라 양쪽에서 상쇄 — 제외)
예측 격차 = 1,038.2 − 942.2 = +96.0원  ⇒  실측 95.64원 ✅
```

**세부 검산 1건 (204840, 09:04:48) — 다섯 층이 같은 거래를 서로 다른 숫자로 기록한다**

```
strategy 로그  매도 시그널 @4,680 (MA20 이탈)            <- 전일 확정 일봉
VTM 로그       138주 @4,510 (총 622,380)                 <- 실제 체결가(장중 현재가)
DB             profit_loss −41,400  profit_rate −0.062370 <- gross + «소수»
FM 로그        투자 회수 663,780 / 매매 손익 반영 −42,713  <- net
strategy 로그  [PAPER] 매도 체결 @4,510 (−6.2%)          <- 정상 표기
```
차 1,313원 = 663,780×0.00015 + 622,380×0.00015 + 622,380×0.0018 = 99.57 + 93.36 + 1,120.28 **정확히 일치.**

#### (c) 잘 된 것

1. **페이퍼 매도의 「중복 매도」 멱등키가 DB 레벨에 실재한다.** `idx_virtual_trading_unique_sell UNIQUE (buy_record_id) WHERE action='SELL' AND buy_record_id IS NOT NULL`(**관리자 DB 실측 확인**). `db/repositories/trading.py:305-311` 의 SELECT-then-INSERT 는 경쟁에 취약하지만 `:373-380` 의 `except psycopg2.IntegrityError → rollback → "Race condition 차단"` 이 **DB 를 최종 심판으로** 쓴다. **장부 멱등성을 애플리케이션이 아니라 스키마에 맡긴 것.**
   > ⚠️ **검수 단서** — 「이 코드베이스에서 가장 좋은 설계 결정」이라는 평가는 **「DB 를 최종 심판으로 썼다」까지만** 유효하다. 그 옆에서 `IntegrityError` 를 잡아 **`return False` 로 끝내고 WARNING 1줄이 전부**라 **호출자는 그 False 와 「진짜 실패」를 구분하지 못한다** — **반환값 계약은 결함으로 따로 세야 한다.**
2. **소유권 정규화가 「원장 키」 층에서 한 번 더 방어된다.** `core/trading_context.py:529` 가 매수 직후 슬롯 owner 를 **클래스명**으로 덮어쓰는데, `_resolve_position_owner`(`virtual_trading_manager.py:493-529`)가 **3단**(호출자 폴더키 → `(code, buy_record_id)` 소유자 → 유일 소유자)으로 **폴더키로 되돌리고 DB 라벨까지 교체**한다. 09-14 실증: `452190` 당일 왕복인데 SELL 행 라벨이 `book_pullback_ma5`(폴더키). **이 방어가 없으면 그 행은 GROUP BY 에서 새 버킷이 되어 재기동 시 그 전략 현금이 영구 손실**된다.
3. **매수 수수료를 「매도 시 1회」만 인식한다는 결정이 명문화·일관 적용돼 있다.** `core/fund_manager.py:330-360` 의 「되돌리지 말 것」 주석과 실제 산식이 **4곳에서 일치**(`order_monitor.py:411-414` · `order_timeout.py:229-232` · `trading_decision_engine.py:912-915` · `trading.py:159-166`).
4. **「유령 체결」 차단이 반환값 계약으로 고정돼 있다.** `execute_virtual_buy` 는 VTM 거부 시 False 를 돌려주고, 호출자가 **반드시** `fund_manager.cancel_order(_reserve_id)` 로 예약을 환원한다(`trading_analyzer.py:309-315`). **2026-06-11 일 4,300만원 오염의 재발 방지책이 계약으로 박혀 있다.**

#### (d) 구조적 약점 + 「이대로 두면 어떤 사고」

**약점 ⑤-1 — 「주문 원장」의 SSOT 가 모드마다 다른 층에 있고, 전환 시 층이 통째로 바뀐다.**

| 모드 | 주문 원장 SSOT | 체결 판정자 | 멱등키 |
|---|---|---|---|
| 페이퍼(현행) | **없음**(Order 객체 자체가 생성되지 않음) | VTM(자기 자신) | DB 부분 유니크 인덱스(**매도만**) |
| 실전 | 메모리 `pending_orders` | **브로커 응답** | **없음** |

> **사고 시나리오** — 실전 첫날 `order_monitor` 상태머신·타임아웃·부분체결·오탐복구가 **첫 실행**된다. 이 경로는 페이퍼 100일치 로그로 **단 1줄도 검증된 적이 없다**. **「페이퍼에서 잘 돌았다」는 ⑤ 에 대해서는 증거가 아니다.**

**약점 ⑤-2 — 실전 원장에는 멱등키가 «하나도» 없다(페이퍼에는 있는데).**
**관리자 DB 실측**: `real_trading_records` = PK + **FK(`buy_record_id → id`)** · **UNIQUE 0** / `real_trading_rs_leader` = **PK 만**(FK 0 · `real_trading_records_id_seq` **시퀀스 공유** · 0행) / `virtual_trading_records` = PK + FK + **부분 UNIQUE 존재**.
`_save_real_trade_to_db` 를 두 번 부르면 **행이 두 개 생긴다.** 그리고 그 경로는 실제로 두 번 불릴 수 있다(→ X1).
> **사고 시나리오** — 매수 1건이 2행 → 다음 기동 대사 「DB 에만 존재」 → **`LiveStartupAbort`**(`state_restorer.py:1203`) → **런북 부재**(기존 P2-29) → **그날 봇 미기동 + 실포지션 무보호.**

**약점 ⑤-3 — 체결 후처리가 「부분 성공 = 정상 종료」로 보인다. 페이퍼도 마찬가지고, 페이퍼는 매일 9~20건이 이 경로를 탄다.**

*페이퍼 «매도» 5단계* (`core/trading_decision_engine.py:888-942`)

| 순서 | 단계 | 예외 격리 | 실패 시 남는 불일치 |
|---|---|---|---|
| ① | VTM 메모리 원장 | 상위 except → ERROR + False | 롤백 없음. 여기서 죽으면 ②~⑤ 미실행, POSITIONED 잔류 → 다음 루프가 재시도 → **사실상 자가치유** |
| ② | DB INSERT | except → WARNING, **db_saved=False 인데 함수는 True 반환** | **메모리는 팔았고 DB 는 안 팔았다.** pending queue → 3회 재시도 → `logs/pending_sells_fallback.json` → **그 파일을 읽는 코드가 0개**(X15) |
| ③ | 슬롯 정리 + COMPLETED | except → WARNING | 원장·DB 는 팔렸는데 슬롯 POSITIONED 잔류 → **다음 루프가 같은 종목을 또 판다**. ①에서 owner 는 이미 pop ⇒ **X14 발화** |
| ④ | FM release/adjust_pnl/remove/cooldown | except → ERROR | **자금만 미반영**: invested 과대·available 과소 → 실전이면 **과소매수**. 페이퍼는 다음 기동 `_resync_fund_manager_to_ledger` 가 **조용히 덮어써 증거까지 지운다** |
| ⑤ | 전략 `on_order_filled` | except → WARNING | 전략 `self.positions` 에 종목이 **남는다** → 그 전략은 팔린 종목을 계속 보유로 알고 재매수 가드가 계속 걸린다. **다음 재기동까지 자가치유 없음** |

*페이퍼 «매수» 5단계* — ①FM 예약 실패 → 스킵(안전) ②DB INSERT 실패 → rid=None → 메모리 무변경 → False → 예약 환원(**원자적, 잘 됨**) ③메모리 원장 예외 → DB 행만 남고 원장 미차감 = **현금 과대**, 다음 기동 리플레이가 DB 기준이라 **자가치유** ④슬롯/tp/sl + 전략 콜백 예외는 **삼킴** → tp/sl 미기입이면 **손익절 판단 불가(무보호)** ⑤FM confirm 예외 → 예약 환불되지만 **②③④ 는 이미 확정** ⇒ 포지션은 있고 **FM invested 미증가 = 가용 과대**.

> 🔑 **핵심 대칭 판정**: **매수는 DB-우선이라 예외가 나도 다음 기동이 고친다. 매도는 메모리-우선이라 예외가 나면 다음 기동이 «거꾸로» 고친다(이미 판 걸 다시 들고 시작한다).** 이 비대칭이 ⑥의 진실원 충돌로 그대로 이어진다.

**약점 ⑤-4 — FundManager 매수 측 연산이 «전부 무로그»라 자금 사고의 사후 재구성이 불가능하다.**
`reserve_funds`(성공 시 로그 없음) · `confirm_order`(diff<0 일 때만) · `add_position`(없음).
> **사고 시나리오** — 실전에서 예약 누수가 나면 **「언제 어느 주문이 예약을 잡았는가」를 로그로 복원할 수 없다.**

**약점 ⑤-5 — 수수료·세금의 「원장별 정의」가 통일돼 있지 않다 — 같은 컬럼 이름이 다른 뜻이다.**

| 원장 | `profit_loss` | `profit_rate` | 근거 |
|---|---|---|---|
| `virtual_trading_records` | **gross** `(sell−buy)×qty` | **소수** `(sell−buy)/buy` | `trading.py:365-366` |
| `real_trading_records` | **net**(매수·매도 수수료 + 거래세 차감) | 소수 `net/buy_cost` | `trading.py:160-167` |
| FM `adjust_pnl` / 로그 `매매 손익 반영` | **net** | — | `trading_decision_engine.py:912-915` |

> **사고 시나리오** — 실전 전환 후 「전략별 손익」을 두 표에서 이으면 **페이퍼 구간은 gross, 실전 구간은 net** 이 된다. 09-14 실증 차 1,313원(위 검산). ⇒ **EOD 보고의 「실현손익 net」 규칙은 유지하되, 두 표를 잇는 계열 그래프는 반드시 기준을 명시해야 한다.**

#### (e) 신규 결함

| # | 결함 | 위치 | 모드 | 검수 판정 | 심각도 |
|---|---|---|---|---|---|
| **X1** | 부분체결 타임아웃 **취소 실패** → 오탐복구가 **무가드 `reverse_confirm`** → 예약 이중계상 + **타 포지션 invested 오염** + 원장 이중기록 | `core/orders/order_timeout.py:263-285` ↔ `core/orders/order_monitor.py:121-223` ↔ `core/fund_manager.py:388-395` | **실전** | **CONFIRMED · 원문보다 «더 나쁘다»** | **P1** |
| **X2** | 실전 원장 **유니크 제약 0**(페이퍼엔 매도 멱등키 존재). X1 의 **전제** | DB + `db/repositories/trading.py:49-52` | 실전 | **CONFIRMED(DB 재현)** + **CR-2** | **P1** |
| **X14** | 원장 귀속 실패 매도 = **대금 2중 소멸**(메모리 + 리플레이) + DB 라벨 클래스명화 | `core/virtual_trading_manager.py:745-763`, `:561-562` | 페이퍼 | **CONFIRMED(경로)** · 도달성 미검증(클래스명 라벨 DB 0건) | P2 |
| **X15** | `pending_sells_fallback.json` = **읽는 코드 0개 데드레터** + `'w'` 비원자적 덮어쓰기 | `core/virtual_trading_manager.py:81`, `:893-916` | 페이퍼 | **CONFIRMED(미발화 — 파일 부재)** · **09-08 `ARCHIVE_INDEX.md` 절단과 같은 클래스** | P2 |
| **X28** | `가상 매도:` 로그 수익률 **100배 축소**(소수를 %로 표기) | `db/repositories/trading.py:366` → `:381` | 공통 | **CONFIRMED** · 09-14 `−0.06%`(실제 **−6.24%**) | P3 |
| **X31** | 실전 원장 `fee_amount`/`net_profit`/`net_profit_rate` 를 **현행 writer 가 안 채운다** | `db/repositories/trading.py:111-113`(매수) · `:172-176`(매도) | 실전 | **CONFIRMED** · 세 컬럼은 DB 에 **실재**(double precision), 레거시 224행은 전부 non-NULL | P3 |
| **X32** | `is_test` 정보량 0 · `source` 는 **DB명 상수**라 페이퍼 인스턴스 구분 불가 | `db/repositories/trading.py:270`(매수) · `:375`(매도) 하드코딩 `true` | 공통 | **CONFIRMED** · DB 실측 조합 **1개**(`kis_template / t`) | P3 |
| **X33** | `LIKE … INCLUDING ALL` 이 **FK 도 못 가져온다** | `db/repositories/trading.py:49-52` | 실전 | **CR-2 · 검수자 신규** | P3 |

**X1 — 전 단계 코드 확인 (검수가 원문보다 «악화»로 판정)**

1. `core/orders/order_timeout.py:263-285` — `if not cancel_success:` 분기가 CRITICAL 로그 후 `order.original_quantity = order.quantity` / `order.quantity = filled_qty` / `status = FILLED` / `_move_to_completed` / `_save_real_trade_to_db` 를 하고 **`fund_manager` 블록(`:287-300`)을 통째로 건너뛴다** ⇒ **`confirm_order` 미호출**.
   *(검수 정정: C 는 「`order.quantity` 를 변조」라 했는데 코드는 `original_quantity` 에 원값을 **보존**한다. 다만 `order_db_handler` 가 읽는 것은 `quantity` 라 결론은 유지.)*
2. `core/orders/order_base.py:142-161 _move_to_completed` — 자금 조작 없음, `_unregister_active_order` 만.
3. `core/orders/order_monitor.py:121-181 _check_false_positive_filled_orders` — `completed_orders[-20:]` 중 `status==FILLED`, 매수는 **1800초 이내**(타임아웃은 300초라 **약 25분간 스캔 대상**). 판정식 `if (filled_qty == 0 or remaining_qty > 0 or is_actual_unfilled) and cancelled != 'Y'` — **취소 실패 = `rmn_qty > 0` & `cncl_yn != 'Y'` = 정확히 이 조건.**
4. `:183-223 _restore_false_positive_order` → `:207-211 fund_manager.reverse_confirm(order.order_id, filled_price * order.quantity)`.
5. `core/fund_manager.py:388-395` — `invested_funds = max(0, invested − amount)` / `order_reservations[order_id] = amount` / `reserved_funds += amount`. **가드 0줄.** (대조: 바로 위 `confirm_order:365-367` 에는 「예약되지 않은 주문이면 경고 후 return」 가드가 **있다** — **쌍이 되는 두 함수의 방어가 비대칭이다**.)

🔴 **검수가 추가한 «더 나쁜 점» 2가지**
- 취소 실패 분기는 주석대로 **예약자금을 «일부러» 유지**한다 ⇒ `order_reservations[order_id]` 가 **살아 있다**. 따라서 `reverse_confirm` 은 「없던 예약을 창조」가 아니라 **살아 있는 예약을 부분체결 금액으로 «덮어쓰고»(원 예약액 소실) `reserved_funds` 에 같은 금액을 «두 번째로» 더한다.**
- `invested_funds −= amount` 는 이 주문이 invested 에 넣은 적 없는 금액이므로 **다른 포지션의 invested 를 깎는다.** `max(0, …)` 는 음수만 막을 뿐 오염은 못 막는다.

⇒ 정합성 등식 `total == available + reserved + invested` 가 **약 2×amount** 만큼 깨진다. **탐지 수단은 그날 저녁 EOD 정합성 검증 CRITICAL 하나뿐이고, 그 시점엔 이미 원장이 이중기록돼 있다.**
그리고 **잔여분이 나중에 체결되면 `_handle_full_fill` 이 또 한 번 `_save_real_trade_to_db`** → 같은 주문의 매수행 2개 → **X2(유니크 0) 때문에 DB 가 막지 못한다** → 다음 기동 `LiveStartupAbort`.

- **선행 감사와의 구분** — 기존 **P1-5**(오탐복구가 «정상 체결»의 부작용을 역산하지 않는다)와 **부호가 반대**다. 여기는 **애초에 부작용이 «없었던»(confirm 미호출) 주문을 역산**한다. 별개 경로.
- **재현법(실행 금지)**: 실전 매수 지정가 → 부분체결로 5분 경과 → `_cancel_remaining_only` 3회 전부 실패 → 30초 뒤 `_check_false_positive_filled_orders` 1주기 관찰. **코드만으로도 판정 가능**(경로 존재 + 무가드 + 판정식 일치는 읽기로 확인됨).
- **수정안(제안)**: ①`reverse_confirm` 에 「예약/확정 이력 없으면 no-op + ERROR」 **가드 2줄** ②취소 실패 분기에서 `order.quantity` 대신 **`filled_quantity`** 를 쓰도록(원인은 `order_db_handler.py:151,193` 이 `quantity` 를 읽는 것) ③`real_trading_records` + 인스턴스 표에 **매도 멱등키 마이그레이션**(X2). **전부 페이퍼 동작 영향 0.**

**X2 · X33 — 관리자 DB 실측 + 검수 정정 2건**

```
real_trading_records   : pkey(id) · idx_action · idx_(stock_code,timestamp DESC) · idx_timestamp DESC   → UNIQUE 0
                       + real_trading_records_buy_record_id_fkey  FOREIGN KEY (buy_record_id) → id     ★ FK 는 «있다»
real_trading_rs_leader : pkey(id) · action_idx · (stock_code,timestamp)_idx · timestamp_idx            → UNIQUE 0 · FK 0
                         id DEFAULT = nextval('real_trading_records_id_seq')  → 시퀀스 공유 · 0행 (parent 224행)
virtual_trading_records: pkey + idx_virtual_trading_unique_sell UNIQUE (buy_record_id)
                         WHERE action='SELL' AND buy_record_id IS NOT NULL                             ★ 존재
```
- **정정 1(C 에게)** — `LIKE … INCLUDING ALL` 이 못 가져오는 것은 「부모에 없는 인덱스」만이 아니다. **PostgreSQL 의 `LIKE` 는 외래키를 복사하지 않는다** ⇒ 자식 표는 유니크뿐 아니라 **참조무결성도 없다**. **C 보다 더 나쁘다.**
- **정정 2(기존 P3-40 에게)** — 「`real_trading_<id>` 가 시퀀스 공유·**FK 없음**」 중 「FK 없음」은 **부모 표에 대해서는 틀렸다**(FK 실재). **자식 표에 대해서만 참.** 시퀀스 공유는 참. 그 항목의 **「DB 미재현」 딱지는 이제 떼도 된다.**

**X14 · X15 · X28 · X31 · X32 — 시나리오·수정안(제안)**

- **X14** — `_resolve_position_owner` 가 None 이면 `else: update_virtual_balance(net_received, "매도")` 로 빠지는데, **전략 원장 모드에서 `virtual_balance` 는 파생값**(`:561-562` 가 `sum(_strategy_balances)` 로 덮어씀) ⇒ **다음 매도 1건이 성공하는 순간 그 대금이 통째로 소멸**한다. 동시에 DB 라벨이 클래스명으로 남고 `restore_strategy_ledger_from_records` 의 `active_keys` 필터가 그 키를 **무시** ⇒ **재기동 리플레이에서도 영구 소실**. **메모리에서 한 번, DB 리플레이에서 또 한 번.** **수정안**: None 이면 **매도를 거부(False)** 하거나 최소한 `logger.critical` + 텔레그램 + 보류. **지금은 INFO 한 줄도 없이 지나간다 — 그게 진짜 문제다.**
- **X15** — grep 전수(archive·tests 제외) 히트 6건 **전부 자기 자신**이고 유일한 읽기는 **자기 쓰기의 append-merge**. 기동 시 로드하는 코드도 조회 도구도 **없다**. 그리고 `:907-908` 이 원본을 **`'w'` 로 직접 연다** — 🔴 **2026-09-08 `ARCHIVE_INDEX.md` 0바이트 truncation 과 정확히 같은 클래스**(read-modify-write + 비원자적 `'w'` + 유일본). **수정안**: ①기동 시 로드해 DB 재삽입 시도 ②**임시파일 → `os.replace()`** ③CRITICAL 승격.
- **X28** — 소비자 0건이라 **동작 영향 0, 로그 오독 위험만**. 그러나 **EOD 수작업 점검이 매일 이 줄을 읽는다**. **수정안**: `{profit_rate*100:+.2f}%` **1줄**.
- **X31** — 매수 INSERT 컬럼 = `(stock_code, stock_name, action, quantity, price, timestamp, strategy, reason, created_at)`, 매도 = `(… profit_loss, profit_rate, buy_record_id, created_at)` — **셋 다 없다.** ⇒ **전환 후 신규 구간만 통째로 NULL.**
- **X32** — **시나리오**: 페이퍼 인스턴스를 하나 더 띄우면(후보선정 A/B 등) 두 봇의 매매가 **같은 버킷에 섞이고**, `get_strategy_trade_sums` 전이력 리플레이가 두 봇 현금을 합산해 **양쪽 원장이 동시에 틀린다**. 실전은 표 이름으로 분리돼 있으나(`real_trading_<id>`) **페이퍼에는 그 장치가 없다.**
- **중복 참조** — 기존 **P1-6**(`status_unknown`) · **P1-7**(매도 부분체결 미분기) · **P2-13** · **P2-27**(`save_real_sell` 존재성 술어) 전부 이 단계에 걸린다. **재발견하지 않았다.**

#### (f) 고수 권고 3줄

| 층 | 권고 |
|---|---|
| **지금 당장** | `db/repositories/trading.py:381` 의 `{profit_rate:+.2f}%` → `{profit_rate*100:+.2f}%`(X28, **1줄 · 동작 0**). EOD 수작업 점검이 매일 이 줄을 읽는데 **100배 작게** 보인다. |
| **실전 전환 전** | **P1 두 건이 여기 있다.** ①`core/fund_manager.py:388 reverse_confirm` 에 **가드 2줄**(X1) ②`real_trading_records` + 인스턴스 표에 **매도 멱등키 UNIQUE 마이그레이션 + FK 명시 생성**(X2·X33). **이것 없이는 「부분체결 + 취소실패」 한 번이 원장을 이중기록하고 다음날 기동을 막는다.** 둘 다 **페이퍼 동작 영향 0**(실전 전용 경로). |
| **장기** | ⑤ 를 **주문 원장 한 층으로 통일**한다 — **페이퍼도 `Order` 를 만들어 `pending → completed` 상태머신을 매일 태울 것.** 지금은 실탄을 다루는 코드의 실사용 검증이 **세션 0회**다. |

---

### ⑥ 재기동 복원 (프로그램 종료 → DB 읽어 보유종목 메모리 로딩)

#### (a) 실제 흐름 사슬

```
main.py 기동
 └ bot/initializer.py.initialize_system
    ├ core/virtual_trading_manager.py:94  _load_paper_eod_balance() → paper_trading_state 최신행 이월
    │                                      (!) 그 값은 «바로 아래에서» 버려진다
    ├ allocate_strategy_capital ×8 (:219-254) → WARNING "전략 자금 할당이 carryover 집계를 덮어씀"
    ├ _initialize_fund_manager                → FM total = 8×10,000,000 = 80,000,000
    └ bot/state_restorer.py.restore_todays_candidates(:77)
       ├ :83  _restore_candidates(today)   ← candidate_stocks, «날짜만» 조회(인스턴스 컬럼 없음) · owner 안 넘김
       └ :87  _restore_holdings_from_db()  [페이퍼]  /  :89 _restore_holdings_from_real_account()  [실전]  ★ 모드 분기점
          ├ :593  db.get_virtual_open_positions()      ← «존재성 술어»(trading.py:428-448)
          ├ 루프(:615-759) 슬롯 생성 → set_position → owner 바인딩 → tp/sl → days_held(:391 «재계산»)
          │                → POSITIONED 전이 → FM add_position/confirm → VTM 잔고 동기화
          ├ :762  _sync_strategy_positions(by_owner) → strategies/base.py:724 sync_positions
          ├ :765  _reconstruct_strategy_ledger(:280-310)
          │        ├ db.get_strategy_trade_sums()            ← ★ virtual_trading_records «전 이력» 리플레이
          │        ├ vtm.restore_strategy_ledger_from_records(:367-475)
          │        │     cash     = 10,000,000 − buy_gross×(1+c) + sell_gross×(1−c−t)
          │        │     invested = Σ qty × buy_price × (1+c)   (미청산분)
          │        ├ vtm.recalculate_investment_amounts(:300-366)   ← 복리 재산정 8건
          │        └ _resync_fund_manager_to_ledger(:312-360)       ← FM total := cash + reserved + invested
          ├ :767  "[가상매매] 보유 종목 N/M개 복원 완료"
          └ :768  _log_fund_sync_summary
       [실전] :1170 broker.get_holdings() + :1180 db_manager.get_real_open_positions()  ← fail-closed 대사(수량만)
              :1044-1085 고아 레그 3분류(미선언=abort / 선언·미로드=격리 / 무기명=격리)   ← (c)-6 참조
main.py:273  _initialize_strategy() → strategy.on_init() 이 self.positions = {} 로 «지운다»
main.py:280  apply_pending_strategy_positions() → «재주입»(state_restorer.py:178-210)
main.py:289  rescan_orphans_after_init()
```

**문서 ↔ 코드 괴리 3건**

| # | 괴리 |
|---|---|
| D-⑥1 | `virtual_trading_manager.py:92` 주석 「전일 EOD 잔고 이월」 — **8전략 구성에서는 이월이 성립하지 않는다.** 09-14 로그가 증언: `가상 잔고 이월 … 23,022,071원` → **5줄 뒤** `전략 자금 할당이 carryover 집계(23,022,071원)를 덮어씀`. ⇒ **`paper_trading_state` 는 복원의 «입력» 이 아니라 EOD 검증의 «기대값» 일 뿐이다.** |
| D-⑥2 | `docs/OWNERSHIP_MODEL.md` 의 「폴더키/클래스명 2종 신원」이 복원 경로에는 **1종만** 온다(DB `strategy` = 폴더키). 그런데 매수 직후 `trading_context.py:529` 가 슬롯 라벨을 **클래스명으로 뒤집으므로** 같은 슬롯의 신원이 **「복원 직후」와 「첫 매수 이후」에 다르다.** |
| D-⑥3 | `bot/eod_benchmark.py:28` 은 「`paper_trading_state.eod_balance` 는 **현금만**이라 못 쓴다」고 적어 뒀는데, `virtual_trading_manager.py:96-97` 은 그 값을 `initial_balance`(레거시 모드 수익률 **분모**)로도 쓴다. |

#### (b) 09-14 실측 대조 (07:40 기동)

| 항목 | 실측 | 대조 |
|---|---|---|
| `가상 잔고 이월` 07:40:10 | **23,022,071원** | DB `paper_trading_state` 09-11 `eod_balance = 23,022,071.31` ✅ |
| 직후 WARNING | `전략 자금 할당이 carryover 집계를 덮어씀` | D-⑥1 — **이월값 폐기 확인** |
| 복원 | `보유 종목 36개 복원 시작` 07:40:11 → **`36/36개 복원 완료`** 07:40:25(**14초**) | ✅ |
| `[sync_positions]` 합 | ma20 5 · rs_leader 9 · ma5 5 · daytrading 4 · elder 10 · minervini 3 = **36** | = 36 ✅ **(단 이 덧셈을 하는 코드는 없다 — X29)** |
| `[재주입] … 6개 전략` | 07:40:25 | 재주입 동작 확인 |
| `전략 원장 재구성 완료: 8개 전략 (집계 23,022,071원)` | — | 리플레이 결과 = `paper_trading_state`(같은 산식) |
| `종목당 투자금액 재산정` | **8건** | 8전략 전부 발화 ✅ |
| `FundManager 원장 재동기화: 80,000,000 → 64,723,356 (현금 23,022,071 + 예약 0 + 투자 41,701,285)` | — | 검산 ✅ |
| `[진단] 런타임 포지션 엔트리 36건 / 고유 36종목 / owner없음 0` | — | FM 레지스트리 정상 |
| 보유 36 → 마감 33 | 36 − 9 + 6 = **33** ✅ | `paper_strategy_equity` `n_open` 합 = **33** ✅ |
| `paper_trading_state` UPSERT | 15:00:02 · 15:35:03 · 16:34:28 (**3회**, 값 전부 23,330,262) | EOD 청산 훅 1 + 스냅샷 전 재저장 2 |
| EOD equity 스냅샷 | 15:35:06 · 16:34:31 (**2회**), 둘 다 `cash_match ✅` | **09-11 행 8개 `updated_at` = 09-14 16:34:31** — 과거 재작성(X 아래 약점 ⑥-3) |
| Σ `paper_strategy_equity` 09-14 `equity` | **64,081,139.64** | = EOD 보고 총자산 **64,081,140** ✅ |
| 복원 owner 미해석 | **0건** | — |
| `candidate_stocks` 복원 | `오늘(2026-09-14) 후보 종목 없음` | 표가 죽어 있음(D-①3) |

**복리 재산정 8건 실측 (`_strategy_initial` 분모 = 영구 10,000,000 고정)**

| 전략 | base | → per_stock | ratio | 재산정 「자본」(**원가** 기준) |
|---|---:|---:|---:|---:|
| book_envelope_200d | 2,000,000 | 1,429,421 | 0.7147 | 7,147,105 |
| book_pullback_ma20 | 2,000,000 | 1,628,845 | 0.8144 | 8,144,224 |
| book_pullback_ma5 | 2,000,000 | 1,583,322 | 0.7917 | 7,916,609 |
| daytrading_3methods_breakout | 2,000,000 | 1,965,797 | 0.9829 | 9,828,985 |
| deep_mr_dev20 | 2,000,000 | 1,276,354 | 0.6382 | 6,381,768 |
| elder_ema_pullback | 500,000 | 435,915 | 0.8718 | 8,718,304 |
| minervini_volume_dryup | 3,333,333 | 3,337,630 | 1.0013 | 10,012,889 |
| rs_leader | 1,000,000 | 657,973 | 0.6580 | 6,579,729 |

리플레이 검산(rs_leader): `10,000,000 − 145,265,645×1.00015 + 138,191,296×0.99805 = 2,634,388.2` = DB `paper_strategy_equity` 09-14 `cash = 2,634,388.13` ✅

#### (c) 잘 된 것

1. **전략별 현금을 「매매기록의 순수 함수」로 정의했다.** 별도 영속화 표 없이 전 이력에서 재계산(`virtual_trading_manager.py:367-475`). **표를 하나 덜 쓰고 대신 재현성을 얻었다** — 순수 함수는 **언제든 감사 가능**하다(위 검산이 그 증거).
2. **`on_init` 이 복원을 지우는 문제를 「재주입」으로 정면 해결했다**(`main.py:280` + `state_restorer.py:178-210`). `sync_positions` 가 `dict.update()` 라 **멱등**이라는 근거까지 주석에 있다. 09-14 실측: `[sync_positions]` 가 **두 번씩** 찍히고 `[재주입] … 6개 전략` 으로 마감.
3. **`flat boot`(보유 0건)에서도 원장 재구성을 «반드시» 태운다**(`state_restorer.py:596-606`). 조기 return 하면 8×10M 이 확정되어 **누적손익이 통째로 소멸**한다는 것을 주석이 **숫자로** 적어 뒀고(`−5,053,250 → 74,946,750 이어야 하는데 80,000,000`), **「세션 로그 100개 중 40개가 flat boot」이라는 도달성 근거까지** 있다. **드문 경로를 「드물지 않다」고 실측으로 반박한 것 — 모범적이다.**
4. **`entry_time` tz 정규화**(`:124-149`). 없으면 `count_trading_days_between` 이 `TypeError` 로 on_tick 을 깬다. 실패 시 None(전략은 hold_days=0 안전 처리) — **fail-safe 방향이 맞다.**

#### (d) 구조적 약점 + 「이대로 두면 어떤 사고」

**약점 ⑥-1 — 「진실원 우선순위」가 «한 방향»으로만 정의돼 있고 역방향 충돌에 대비가 없다.**

```
1. virtual_trading_records (전 이력)  ← 절대 우선. 포지션·현금·tp/sl·owner 전부 여기서 나온다
2. paper_trading_state.eod_balance    ← 읽지만 즉시 버려짐. EOD cash_match «기대값»으로만 생존
3. paper_strategy_equity              ← 복원에 «전혀» 쓰이지 않음. 순수 출력물
4. 메모리                              ← 전량 폐기
```
**깨지는 경우 3가지** — (a) **메모리가 팔았고 DB 가 모른다**(X15) → DB 가 이기므로 **이미 판 종목을 다시 들고 시작한다** (b) **DB 라벨이 잘못됐다**(X14) → `active_keys` 필터가 그 행을 **무시**하므로 현금이 영구히 틀리고 **페이퍼엔 대사 상대가 없어 영원히 발견되지 않는다** (c) **과거 행이 수정·삭제됐다** → 전이력 리플레이라 **어제 기록을 오늘 고치면 오늘 현금이 바뀐다**.
> **셋 다 「조용히」 깨진다 — 페이퍼에는 계좌 대사 상대가 없기 때문이다.** (실전은 반대로 대사가 fail-closed 라 **「기동 중단」**으로 나온다.)

**약점 ⑥-2 — 복리 재산정(cost basis)과 equity 스냅샷(mark-to-market)이 «다른 양»인데 둘 다 「자본」이라 불린다.**

| 전략 | 재산정 「자본」(원가) | equity 09-11(시가) | 미실현 |
|---|---:|---:|---|
| book_pullback_ma20 | 8,144,224 | 8,143,493.41 | 평가손 소액 |
| book_pullback_ma5 | 7,916,609 | 7,927,845.93 | 평가익 +11,237 |
| daytrading_3methods | 9,828,985 | 9,451,153.53 | **평가손 −377,831** |
| elder_ema_pullback | 8,718,304 | 8,762,969.07 | 평가익 +44,665 |
| minervini_volume_dryup | 10,012,889 | 10,449,726.47 | **평가익 +436,837** |
| rs_leader | 6,579,729 | 6,459,461.33 | 평가손 −120,268 |
| **Σ** | **64,729,613** | **64,723,522** | **−6,091** |

> ⚠️ **인용 주의(검수 지적)** — 원문 C 의 표는 「차 = 원가 − 시가」라 **평가익이 음수로 보인다**. 위 표는 **부호를 바로잡아** 다시 적은 것이다.
> ⇒ **「진짜 복리」(2026-07-29 결재)는 «실현손익 복리»이지 «자본 복리»가 아니다.** `minervini` 는 시가 기준 **+436,837 평가익을 없는 것으로 치고** per_stock 3,337,630원을 산정했고, `daytrading` 은 **평가손 −377,831 을 없는 것으로 치고** 거의 만액(1,965,797원)으로 산정했다.
> **사고 시나리오** — **평가손이 큰 전략이 줄지 않은 사이즈로 계속 산다** → 드로다운이 복리로 확대된다. **Σ 가 −6,091 로 우연히 붙어 있어 총계로는 안 보인다 — 전략별로 봐야만 드러난다.**

**약점 ⑥-3 — equity 스냅샷이 «불변 기록»이 아니라 «매번 전 구간 재작성»이다.**
DB 실측: `paper_strategy_equity` 의 **09-11 행 8개가 전부 `updated_at = 2026-09-14 16:34:31`** — 09-14 EOD 실행이 09-11 행을 다시 썼다.
> **사고 시나리오** — **오늘 아침 재기동이 읽은 09-11 equity 를 지금 조회하면 그 값이 아니다.** 사후 검증의 유일한 증거는 로그의 재산정 8줄뿐이고 그건 **cost basis 라 애초에 다른 양**이다. ⇒ **사후 대조가 원리적으로 불가능.**

**약점 ⑥-4 — 세 「총자산」이 서로를 검증하지 않는다.**

| 이름 | 09-14 값 | 정의 | 출처 |
|---|---:|---|---|
| FM `total_funds` | 64,392,301 | VTM 현금 + **순수 매수원가** | `system_monitor` 15:35:03 정합성 검증 |
| Σ `paper_strategy_equity.equity` | **64,081,140** | 현금 + **시가평가** = **EOD 보고 총자산** | DB 실측 |
| Σ VTM 재산정 자본 | 64,729,613 | 현금 + 원가×1.00015 | 07:40 재산정 로그 8줄(09-11 기준) |

그리고 **FM.available 과 VTM.cash 를 대조하는 코드가 운영 디렉토리에 한 줄도 없다**(grep: 「`available_funds` 와 `virtual_balance`/`_strategy_balances` 가 같은 줄」 → **0건**). EOD 정합성 검증은 **FM 내부 등식만**, `cash_match` 는 **둘 다 VTM 계열**이라 **자기 자신과의 비교**다.
> 🔴 **유일한 접점은 매일 아침 `_resync_fund_manager_to_ledger` 가 «강제로 같게 만드는 것» — 불일치를 고치는 게 아니라 «증거를 지운다».** 09-14 마감 96원 격차는 **아무도 보고하지 않았다**(무해한 금액이지만, 보는 코드가 없다는 것이 문제다).

**약점 ⑥-5 — 재기동은 «포지션은 유지하고 브레이크만 전부 푼다».**

| 항목 | 재기동 시 | 위치 | 영향 |
|---|---|---|---|
| 보유 포지션(수량·평단) | **유지**(DB 복원) | `state_restorer.py:654` | ✅ |
| tp/sl | **유지**(종료 시 BUY 행 flush 후 복원) | `initializer.py:812-826` ↔ `state_restorer.py:621-632` | ✅ 페이퍼 한정(실전은 컬럼 부재 = 기존 P1-4) |
| `days_held` | **재계산**(DB buy_time) | `:391` | ⚠️ **재기동 그 자체가 max_hold 판정을 갱신** |
| 전략 `self.positions` | 폐기 후 **재주입** | `main.py:280` | ✅ |
| 전략별 현금/원장 | 전이력 리플레이로 재구성 | `virtual_trading_manager.py:416-424` | ✅ |
| per_stock(복리) | **재산정** | `:300-366` | ⚠️ 장중 재기동이면 그날 매매까지 반영 → **같은 날 사이즈가 바뀐다** |
| **일일 실현손실 한도** | **리셋 → 0** | `fund_manager.py:236-237`(복원 코드 없음) | 🔴 **손실 한도가 되살아난다**(기존 P2-18) |
| **매도 후 재매수 쿨다운** `_sell_cooldowns` | **리셋 → {}** | `fund_manager.py:226` | 🔴 **방금 손절한 종목을 즉시 재매수 가능**(30분 소멸) — **선행 3문서에 없던 신규** |
| 전략 `daily_trades`/`daily_profit` | **리셋**(on_init 전 전략 루프) | `strategies/*/strategy.py:99` | 🔴 전략별 일일 거래 한도가 되살아남 |
| 연속 매도실패 CB | 리셋 → {} | `position_monitor.py:84` | 🟢 이 경우엔 유리 |
| `_candidates_loaded` | 리셋 → False | `candidate_loader.py:39,50` | ⚠️ **장중에 후보를 다시 로드**한다 |
| `_last_eod_liquidation_date` | 리셋 → None | `liquidation_handler.py:52` | ⚠️ 현재 8전략 전부 swing 이라 무해, **intraday 도입 시 되살아남** |
| `pending_orders`/`order_timeouts` | 리셋 | `order_base.py:32-33` | 페이퍼 무영향 / **실전은 기동 시 전량 취소**(기존 P2-20) |
| `_pending_sell_records` | **소실** | X15 | 🔴 파일은 남지만 **읽는 코드가 없다** |

> 🔑 **「위험을 줄이는 상태만 골라서 리셋된다」** — 검수가 **「3편 중 가장 좋은 한 문장」**이라 평가한 구조 판정이다. 유지되는 것은 위험을 **늘리는** 쪽(포지션)이다.
> **사고 시나리오** — 급락일 오전에 손절 5건으로 한도 근접 → 패치 배포 재기동 → **한도 0 · 쿨다운 0** → **방금 손절한 종목을 오후에 다시 사고 또 손절.**
> ⚠️ 단 **급락게이트 같은 시장 축 가드는 매 tick 재평가형이라 재기동 영향이 없다.** 리셋되는 것은 **누적 카운터형 가드뿐**이고, **그게 정확히 리스크 한도들이다.**
> ⚠️ **검수 정정** — 원문 C 가 든 4종 중 `_new_entries_this_cycle` 은 **빼야 한다**(X24 로 그건 **애초에 죽은 가드**, 항상 0). **죽은 값의 리셋은 위험이 아니다** ⇒ 4종 → **3종**, 그중 `_daily_realized_loss` 는 기존 P2-18, `daily_trades` 는 X10 과 중복 ⇒ **진짜 신규는 `_sell_cooldowns` 하나**이고, 그 한 건이 **실전에서 실질 P1** 이다.

**약점 ⑥-6 — 복원 직후 첫 tick 이 «무방비»다.**
`position_monitor.py:219-224` 의 `is_before_rebalancing` 은 **`hour==9 and minute<5`(벽시계)**이고, **손절(`:326`)과 장기보유 손절(`:239`)에만** 적용된다. 미적용: **장기보유 익절(`:227`) · max_holding_days(`:254`) · 목표 익절(`:314`) · 전략 매도신호(`:339`).**

| 순위 | 판정 | 09:00~09:05 유예 | 재기동 직후 즉발 |
|---|---|---|---|
| 1 | 장기보유(30일) 익절 | ❌ | **예** |
| 2 | 장기보유 손절(−3%) | ✅ | 09:05 이후 즉발 |
| 3 | **max_holding_days 초과** | ❌ | **예 — 가장 위험** |
| 4 | 공통 트레일링 | ❌ | 전략 포지션은 미적용 |
| 5 | 목표 익절 | ❌ | **예** |
| 6 | 손절 | ✅ | 09:05 이후 즉발 |
| 7 | 전략 매도신호 | ❌ | **예**(09-14 `204840` 09:04:48 이 실례) |

> **3번이 위험한 이유** — `days_held` 는 복원 시 DB `buy_time` 에서 **매번 새로 계산**된다 ⇒ **재기동 그 자체가 max_hold 판정을 갱신**한다. 휴장일 캘린더가 틀리거나(기존 P2-23·24) 주말을 낀 월요일 기동이면 **여러 종목이 동시에 한도를 넘어 첫 패스에서 일괄 청산**된다. **가격 조건이 전혀 없으므로 갭하락 시가에 그대로 나간다.** 실전은 시장가(`price=0`)라 **슬리피지가 그대로 실현**된다.
> **장중 재기동은 유예가 0초다** — 벽시계 조건이라 13:00 기동에는 무효. 복원 → 12초 뒤 첫 `check_positions_once` → **33종목 전량 즉시 평가.** ⇒ **패치 배포 한 번이 33종목을 던질 수 있다.**

#### (e) 신규 결함

| # | 결함 | 위치 | 모드 | 검수 판정 | 심각도 |
|---|---|---|---|---|---|
| **X12** | 복원 유예가 **벽시계(09:05)** 기준이고 **손절만** 커버 → **장중 재기동 유예 0초** | `core/trading/position_monitor.py:219-224` 적용 `:239`,`:326` / 미적용 `:227`,`:254`,`:314`,`:339` | 공통 | **CONFIRMED** · C-N6 + B-W9 **병합(M1)** · 09-14 손절 43% 가 09:05:10~12 | P2(**실전 P1**) |
| **X13** | **매도 후 재매수 쿨다운(`_sell_cooldowns` 30분)이 재기동에 소멸** | `core/fund_manager.py:226` | 공통 | **CONFIRMED** · C-N5 중 **유일한 진짜 신규** | P2(**실전 실질 P1**) |
| **X29** | **「N/N 복원」 카운터가 전략 주입을 포함하지 않는다** | `bot/state_restorer.py:694`(by_owner 조건) · `:728`(증가) · `:767`(출력) · `:171-172`(조용한 skip) | 공통 | **CONFIRMED** | P3 |
| **X30** | VTM `_strategy_invested` 를 매도 시 **«매도대금»으로 차감** → 세션 중 자본이 손익에 반응하지 않는다 | `core/virtual_trading_manager.py:683-686`(매수 **원가**) ↔ `:751-755`(매도 **대금**) | 페이퍼 | **CONFIRMED(휴면)** | P3 |
| **X34** | 복리 사이징이 **cost basis**(미실현 미반영 · 전략별 최대 **±436,837**) | `core/virtual_trading_manager.py:349-350` vs `paper_strategy_equity` | 페이퍼 | **구조 판정 · DB 재현** | P3(구조) |

**시나리오·재현법·수정안(제안)**

- **X12** — **재현**: 09-14 로그 `grep "손절 실행"` 시각 분포(09:05:10·11·12 3건 = 43%) + `09:04:48 204840 전략 매도신호`(유예 창 **안**에서 통과). **수정안**: 기준을 **「복원 완료 시각 + M초」**(예: 60초)로 바꾸고 **손절·max_hold·익절·전략신호를 전부** 포함. **동작 변경 → 사전등록 + 결재.**
- **X13** — **수정안**: 완충 상태(`_sell_cooldowns` · `_daily_realized_loss`)를 **거래일 키로 영속화**하고 복원 시 **같은 거래일이면 승계**. 코드량은 작지만 **「재기동으로 리스크 한도를 리셋하지 않는다」는 실전 전환 전 반드시 서 있어야 할 불변식**이다. **동작 변경 → 결재.**
- **X29** — 「36/36」은 **「DB 가 준 36행을 36개 슬롯으로 만들었다」**는 뜻이지 **「전략 6개가 36종목을 알고 있다」**는 뜻이 아니다. 후자를 확인하려면 `[sync_positions] … N종목` 6줄을 **사람이 더해 봐야** 하고 **그 덧셈을 하는 코드가 없다**. `_sync_strategy_positions` 는 owner 미해석 시 **조용히 skip** 하는데 `holding_restored` 는 **이미 증가한 뒤**다. 🔑 **2026-08-12 「61종목 복원 성공 로그 직후 보유 없음」 사고가 정확히 이 눈먼 지점이고, 고친 것은 주입 경로이지 카운터가 아니다** — 같은 사고가 나면 **로그는 다시 `N/N` 이라 찍는다**. **수정안**: `_log_fund_sync_summary` 에 **`Σ by_owner == holding_restored` 단언 1줄**(불일치 ERROR). **동작 변경 0.**
- **X30** — 산술 확인: `204840` 원가 663,879.57 vs `net_received` 621,166.36 ⇒ **잔류 42,713.21 = 그 거래의 net 손실액과 정확히 같다**. ⇒ `cash + invested` 가 매도 시 **불변** = **세션 중 「현재 자본」이 실현손익에 전혀 반응하지 않는다.** 현재 무해한 이유는 `recalculate_investment_amounts` 의 유일한 호출자가 **기동 1회**이고 그 시점 값이 리플레이가 만든 깨끗한 값이기 때문. 🔴 **장중 리밸런싱이나 장중 equity 표시를 추가하는 순간 P1 이 된다** — 「손실을 내도 자본이 안 줄어드는 복리」가 된다. **수정안**: `−= min(invested, 원가)` 로 바꾸고 손익은 별도 경로가 전담(FM 관례와 동일).
- **X34** — `_strategy_initial` 분모가 **영구히 10,000,000 고정**(`setdefault`)인 것은 「자본이 회복되면 원사이즈로 돌아온다」는 **의도된 설계**이지만, 미실현 미반영은 별개 문제다. **수정안(장기)**: `recalculate_investment_amounts` 가 `paper_strategy_equity.equity` 계열을 읽게. **사이징 변경이므로 결재 · 3전략 성과 계열이 단절된다.**
- **중복 참조** — 기존 **P2-18**(일일 손실 한도 재기동 리셋) **여전함**(X13 과 한 묶음). 기존 **P2-28/29**(유령 잔량 → `LiveStartupAbort` → 런북 부재) **여전함**. 기존 **「`candidate_stocks` 인스턴스 구분 없음」** **여전함**. 기존 **`max_capital_pct` 미배선** **여전함** — 09-14 기동 경고 `합계 122% … provider 주입 + reserve_funds(strategy_name=) 둘 다 있어야 발효 — 미결선`, `bot/trading_analyzer.py:253` 이 `strategy_name=` 을 **안 넘긴다**(계열 6번째).

#### (f) 고수 권고 3줄

| 층 | 권고 |
|---|---|
| **지금 당장** | `_log_fund_sync_summary` 에 **`Σ by_owner == holding_restored` 단언 1줄**(X29). **2026-08-12 사고를 「로그만 보고」 잡을 수 있게 하는 최소 변경**이고 동작 변경 0이다. |
| **실전 전환 전** | ①복원 유예를 「09:05 이전」 → **「복원 완료 + 60초」**로 바꾸고 **손절·max_hold·전략신호까지 포함**(X12) ②`_sell_cooldowns`·`_daily_realized_loss` 를 **거래일 키로 영속화**(X13). **실전은 시장가 매도라 장중 재기동 한 번이 33종목을 갭 시가에 던질 수 있다.** 둘 다 동작 변경 → **결재**. |
| **장기** | **「자본」의 정의를 하나로 못 박는다.** 지금 「총자산」이라 불리는 값이 **세 개**다(FM 원가 64,392,301 · Σequity 시가 64,081,140 · VTM cash+invested 64,729,613). 복리 사이징은 **시가평가 기준**이어야 한다(X34). 같은 이름의 다른 양이 **표 4개·로그 2개**에 흩어져 있다. |

---

## 3. 검수가 정정한 것

> 이 절은 **검토 3편의 원문을 어떻게 고쳐 읽어야 하는지**를 남긴 흔적이다. 강등·철회된 것은 취소선으로 표시했다.
> 🔑 **원칙 재확인** — 「사고가 없었다 ≠ 방벽이 동작한다」를 3편이 각자 **새 통찰인 양** 발명했다. **이건 이 프로젝트의 기존 재사용 규칙(「한 번도 발동 안 함 ≠ 막혀 있다」)이다. 새 통찰로 세지 말 것.**

### 3-1. 철회 (REFUTED)

| # | 원문 주장 | 판정 | 근거 |
|---|---|---|---|
| **R1** | ~~B-10: 「EOD 청산 가드가 fail-open 이라 **실전 첫날 15:00 에 의도치 않은 시장가 전량 청산**이 가능하다. 실전은 전략을 1개만 켜므로 나머지 7전략 소유 포지션이 정확히 그 조건에 들어간다」~~ | **REFUTED** · 위치만 CONFIRMED · **P3 강등**(X27) | **세 겹으로 틀렸다.** ①**폴백이 None 이 아니다** — `bot/liquidation_handler.py:177-178, 265-266` 은 `owner or decision_engine.strategy` 이고 `main.py:238-242` 가 `self.strategy = next(iter(self.strategies.values()))` → `decision_engine.set_strategy(...)` ⇒ **전략이 1개라도 로드되면 두 번째가 채워진다**(관리자 원문 직접 확인). None 이 되려면 **로드된 전략 0개**여야 하고 그러면 봇은 애초에 매매하지 않는다. ②**폴백이 걸려도 청산되지 않는다** — `strategies/base.py:764-777 should_liquidate_eod` 는 `return self.holding_period == "intraday"` 인데 3전략 전부 `swing` ⇒ **False ⇒ 스킵**. ③**그 포지션이 애초에 없다** — 실전 복원은 `broker.get_holdings()` + `real_trading_<id>` 를 읽고, 페이퍼 8전략 포지션은 `virtual_trading_records` 로 **다른 표·다른 계좌**다(DB 실측 `real_trading_rs_leader` **0행**). ④게다가 owner 미해석 레그는 코드가 **이미 「격리」로 명시 처리**한다(`state_restorer.py:1044-1085`). |
| **R2** | ~~기존 **P2-19**: 「미체결 타임아웃이 쿨다운 미무장 → 5분마다 재발주, 종목당 최대 약 75회/일(API 예산 소진)」~~ | **REFUTED** · B-4(X9)가 **정반대**로 대체 | 쿨다운 미무장은 **사실이지만 필요조건일 뿐 충분조건이 아니다** — 재시도가 일어나려면 그 종목이 **다시 매수 루프에 보여야** 한다. 차단 사슬: 타임아웃 → `COMPLETED`(`order_execution.py:478-486`, `enable_re_trading=True` 하드코딩) → 매수 루프는 **SELECTED 만** 순회(`trading_context.py:281`) → `COMPLETED → SELECTED` 복귀는 재선정 분기뿐, **장중 호출자 0**. 재발주 코드 자체도 없다: `grep place_buy_order` 전수 = `order_execution.py:234`(execute_real_buy) + `order_executor.py:587`(`_adjust_order_price`)이고 **후자는 `order_monitor.py:115` 에서 주석 처리돼 호출자 0**. ⇒ **실전 첫날, 지정가가 한 번 안 붙은 종목은 그날 다시 시도되지 않는다.** |
| **R3** | ~~A 의 「지금 당장」 권고 ①: 「스냅샷 훅을 `asyncio.to_thread` 로 내린다」~~ | **권고 철회** | 지적(동기 함수를 async 안에서 직접 호출) 자체는 옳다. **그러나 그 수정이 손절 감시 공백을 «못 고친다».** `main.py:438-440` 이 `await self._load_screener_candidates()` 를 **메인 루프 1~5단계보다 앞에서 순차로 await** 하므로 스레드로 내려도 **그 await 는 그대로 걸리고 1~5단계는 여전히 안 돈다**. `to_thread` 가 살리는 것은 **시스템모니터·텔레그램 태스크**뿐이다. ⚠️ 용어도 틀렸다 — A 가 「세 태스크」라 부른 `collect_once`/`check_pending_orders_once`/`check_positions_once` 는 **태스크가 아니라 같은 루프의 순차 단계**다(실제 태스크는 `main.py:320-325` 의 메인트레이딩루프·시스템모니터링·텔레그램 3개). **유효한 처방은 「08:5x 장전 스냅샷 분리」 하나뿐이다.** |

### 3-2. 수치 정정

| # | 원문 | 정정 | 근거 |
|---|---|---|---|
| **N1** | ~~「LOOP_INTERVAL=3, ON_TICK_EVERY_N=3 ⇒ 9초마다 전략 1개, 8전략이면 한 전략은 **72초**마다 1회」~~ | **약 290초(4.8분)** | 명목값이다. **B 자신의 실측이 자기 주장을 반증한다** — 09:02~15:28 ≈ 23,200초에 72초 주기면 전략당 **약 320회**여야 하는데 실측은 **79~80회**(8전략 전부 재현). 원인은 `main.py:513-517 sleep = max(0, 3 − elapsed)` 가 **항상 0**이고 실제 라운드가 **12.2초**이기 때문. 검산 **12.2 × 3 × 8 = 293초** ✅ |
| **N2** | ~~「09:00 에 이벤트 루프가 통째로 약 **60초** 멈춘다」(A §0 헤드라인)~~ | **34초**(09:00:28 → 09:01:02) | 그 앞 **08:40:37 → 09:00:28 은 로그가 통째로 비어 있다**(20분). `main.py:433-435` 가 장 마감 중 `sleep(30)` 이므로 09:00:00~09:00:28 은 **훅 블로킹이 아니라 30초 폴링 granularity 의 잔여**로 설명된다. **A 자신이 부록에 「미확정」이라 적고 헤드라인엔 60초라 썼다.** |
| **N3** | ~~「API 예산 **100% 포화**(10.1 호출/초)라 호출 하나가 공짜가 아니다」~~ | **근거 무효** | 237,141 회를 「장중 23,400초」로만 나눈 값인데 봇은 **07:40~18:34 가동**이고 **15:46 이후 EOD 분봉 배치(112,926행)가 같은 카운터에 들어간다**. **라운드 산술은 옳지만 일일 총계 나눗셈은 근거로 쓰지 말 것.** 살아남는 검증된 문장 = **「라운드 시간이 호출수에 선형이다」**. |

> **영향 범위** — N1 정정은 B 의 「[A] 3초 vs [B] 72초」·「[A]:[B] = 8:1」 해석·경쟁조건 창 추정에 전부 쓰인다. **[A] 는 약 12초, [B] 는 전략당 약 290초로 정정.** 🔑 **정정 방향은 B 의 결론을 «강화»한다** — 전략 룰 매도가 **더 드물게** 평가된다 = **백스톱 의존도가 더 높다.**

### 3-3. 강등 (OVERSTATED)

| # | 원문 | 강등 | 사유 |
|---|---|---|---|
| **A-N4 → X19** | ~~P2(실전) · 「장중 재기동 → owner="" 복원 → 서로 다른 전략이 각자 매수 → 다중 진입」~~ | **P3** | 확정 모델(1 인스턴스 = 1 계좌 = 1 전략)에서 **「서로 다른 전략」이 없다**. 오히려 반대로 owner 가 비면 그 슬롯은 **그 하나뿐인 전략에게 보인다** ⇒ 기존 P1-2(owner=클래스명이라 아무에게도 안 보임)를 **우회해 주는** 방향 = **위험이 아니라 우연한 완화**. 살아남는 지적은 ①같은 파일 두 복원 경로의 **비대칭**(`:569` vs `:646`) ②표는 죽었는데 reader 는 살아 있는 **감사 함정**. |
| **A-N2 → X18** | ~~P2 · 「후보 상한을 올리면 관리 종목 81 → 약 126 이 되어 120 을 넘는다」~~ | **P3(조건부)** | 실측 관리 수는 **81 이 아니다** — `선정 완료` 누계 81(복원 36 + 신규 45)인데 09:10:41 수집 dict 는 **78종목**이다(09:04~05 매도 3건과 정합). 「폴링 81종목」은 **등록 누계이지 동시 관리 수가 아니다**. 「약 126」은 A 자신이 **추정**이라 밝혔다. **결합 자체는 옳고 반드시 같은 결재에 묶어야 하지만, 아직 일어나지 않은 변경의 하류**다. |
| **A-N9 → X23** | ~~「감사 함정」~~ | **신규 아님 · P3 정리 항목** | **레포가 이미 자기 주석 3곳에 적어 뒀다**(`core/intraday/price_service.py:83-89` · `core/post_market_data_saver.py:11` · `bot/system_monitor.py:387`). 「함정」이라 부르는 건 과장. **「파사드가 public 인데 주석은 안쪽에만 있다」로 한정할 것.** |
| **C-N5 → X13** | ~~「완충 상태 **4종** 이 재기동에 전량 리셋」~~ | **3종 · 진짜 신규는 1건** | `_new_entries_this_cycle` 은 **빼야 한다** — X24 로 그건 **애초에 죽은 가드**(항상 0)이고 **죽은 값의 리셋은 위험이 아니다**. 남은 3종 중 `_daily_realized_loss` 는 기존 P2-18, `daily_trades` 는 X10 과 중복 ⇒ **진짜 신규는 `_sell_cooldowns`(30분 재매수 금지) 하나**. 단 그 한 건이 실전에서 **「방금 손절한 종목 즉시 재매수」**라 **실질 P1**. |
| **C-G1 칭찬** | ~~「부분 유니크 인덱스 = 이 코드베이스에서 가장 좋은 설계 결정」~~ | **칭찬은 「DB 를 최종 심판으로 썼다」까지만** | 그 옆에서 `db/repositories/trading.py:305-311` 이 SELECT-then-INSERT 를 하고 `IntegrityError` 를 잡아 **`return False` 로 끝낸다**. WARNING 1줄이 전부고 **호출자는 그 False 와 「진짜 실패」를 구분하지 못한다** ⇒ **반환값 계약은 결함으로 따로 셀 것.** |
| **C-W7 표** | 「차 = 미실현」 헤더 | **부호 주의** | 원문 표의 차는 **(원가 − 시가)**라 **평가익이 음수로 보인다**. 재인용 시 오독 주의(§2 ⑥ (d) 표는 부호를 바로잡았다). |

### 3-4. 검수자 신규 발견 2건

| # | 발견 | 판정 |
|---|---|---|
| **CR-1 → X17** | **`on_market_open()` / `on_market_close()` 가 8전략 중 1개에만 간다.** `main.py:246-254`·`:256-264` 가 `self.strategy`(단수)에만 콜백하고, `:238-242` 가 `next(iter(self.strategies.values()))` = **dict 첫 전략 = elder**. 호출 지점은 `main.py:440` 하나. **로그 실측이 그대로 증명**: 09-14 전체에서 `장 마감 — 거래` 가 **단 1줄**, `ElderEmaPullbackStrategy`. 대조로 `on_init` 은 `main.py:218-220` 에서 **전 전략 루프**(그래서 기동 시엔 daily_trades 가 전부 0 — **매일 07:40 재기동이 이 결함을 가려 왔다**). | **P2(페이퍼) / 실전 무해** · **X10 의 원인 귀속을 정정한다** — `_candidates_loaded`(P2-25)를 되살려도 **7전략은 콜백을 못 받는다**. **결론은 옳지만 원인이 틀렸고 실제로는 더 나쁘다.** |
| **CR-2 → X33** | **`LIKE … INCLUDING ALL` 이 FK 도 못 가져온다.** `db/repositories/trading.py:49-52` 로 만든 인스턴스 표는 부모에 **있는** `buy_record_id → id` FK 를 **못 물려받는다**(PostgreSQL 의 `LIKE` 는 외래키를 복사하지 않는다). | **P3** · 기존 **P3-40 의 「FK 없음」을 정정** — **부모가 아니라 자식**에 대한 서술이라야 맞다. 시퀀스 공유는 참. **「DB 미재현」 딱지는 뗀다.** |

### 3-5. 병합 (중복 제거)

| 병합 | 구성 | 대표 | 근거 |
|---|---|---|---|
| **M1** 09:05 유예 | C-N6 + B-W9 | **X12** | 같은 실측(손절 3건 09:05:10~12), 같은 코드. C 가 「장중 재기동 0초」까지 확장 |
| **M2** 가짜 분봉 [C] 경로 | A-N8 + B-7 | **X7** | A = 입력이 쓰레기(O=H=L=C·vol 0) · B = 두 전략이 그 입력을 실제로 소비. **한 수정(I5)으로 둘 다 닫힌다** |
| **M3** 일일 리셋 | B-8 + C-N5(daily_trades) + 기존 P2-25 + **CR-1** | **X10**(원인 = X17) | 전부 「거래일 경계 상태 리셋 경로 부재」 |
| **M4** 실전 원장 무결성 | C-N11 + C-N1 + 기존 P3-40 | **X2 · X1** | N11 은 N1 의 전제. **마이그레이션 1건으로 묶어 처리** |
| **M5** 후보 상한·슬롯 한도 | A-N1 + A-N2 | **X4 + X18** | **두 상수를 같은 결재로** |
| **M6** params_hash | A-N3 + A-N6 | **X5 + X6b** | 해시를 고치는 날 X6b 가 발화 |
| **M7** 매도 계수 관측 | C §⑤-5 경고 + B §④-5 표 | — | **모순 아님.** C 의 「`가상 매도 완료 처리` 1건 ≠ 매도 1건」 경고와 B 의 「매도 9건 전수표」는 정합(`가상매도:` 9 = DB SELL 9). **C 의 경고를 EOD 점검 절차에 넣을 것** |

---

## 4. 신규 결함 통합 목록 (검수 재조정 후)

> 기존 40건(`docs/audit_2026-09-14_real_trading_switch.md` · `CRITIC_verify.md §4`)은 **제외**. 아래는 **이 검토에서 새로 나온 것만**이다.
> **동결 판정 기준** — 09-05 계획서의 「룰 라이브 변경 0건」 = `strategies/*/config.yaml` 및 전략 파일의 **판정 로직**. **로그 1줄 추가·프레임워크 계층 수정은 동결 대상이 아니다**(단 관측치가 바뀌면 사전등록).

### P1 (3건)

| # | 항목 | 출처 | 판정 | 모드 | 동결 충돌 |
|---|---|---|---|---|---|
| **X1** | 부분체결 **취소실패** → 오탐복구가 무가드 `reverse_confirm` → 예약 이중계상 + **타 포지션 invested 오염** + 원장 이중기록 | C-N1 | **CONFIRMED(원문보다 악화)** | 실전 | **없음**(실전 전용 경로) |
| **X2** | **실전 원장 유니크 제약 0**(페이퍼엔 존재) — X1 의 전제. 자식 표는 **FK 도 없다** | C-N11 + CR-2 | **CONFIRMED(DB 재현)** | 실전 | **없음** |
| **X3** | `max_positions` 캡 포화가 「룰 미충족」과 **같은 로그** → 3전략 고도화 **계측 분모 오염** | B-1 | **CONFIRMED** | 공통(계측) | **없음**(룰 로직 무변경 · 「계기 추가」로 사전등록 분리 권고) |

### P2 (14건)

| # | 항목 | 출처 | 판정 | 모드 | 동결 충돌 |
|---|---|---|---|---|---|
| X4 | 후보 상한 이중화(생성 20 / 소비 10, 출처 = 비활성 `sample` 파라미터) | A-N1 | CONFIRMED | 페이퍼 | 있음(후보 수 변경) |
| X5 | `params_hash` 가 룰 파라미터 미포함 → ma20/ma5 **동일 해시**(DB 재현) · 집합 차분 무력 | A-N3(+N6) | CONFIRMED | 공통 | 해시 변경 시 **과거 행과 단절 → 사전등록 필수** |
| X6 | 폴링 대상(후보 전량) ≠ 소비(POSITIONED 3곳) → 라운드 12.2초 · 감시 지연이 후보수에 **선형** | A-N7 | CONFIRMED | 공통 | 있음(관측치 변경) |
| X7 | 매도 판단이 O=H=L=C·vol 0 「가짜 분봉」을 보고 **minervini·daytrading 만 그 경로가 열려 있다** | A-N8 + B-7 (M2) | CONFIRMED | 공통 | **없음**(I5 안 기준) |
| X8 | 급락/CB/국면 차단 로그에 **종목·전략·해석지수 없음** → 전략별 귀속 불가(713줄 전수) | B-3 | CONFIRMED | 공통 | **없음**(로그만) |
| X9 | `enable_re_trading=True` 하드코딩 → 미체결 1회로 **당일 기회 상실**. **기존 P2-19 는 철회** | B-4 | CONFIRMED / P2-19 **REFUTED** | 실전 | **없음**(실전 전용) |
| X10 | `daily_trades` 가 **매도까지 셈** + 리셋 경로 없음(**원인 = X17**) | B-8 + CR-1 (M3) | CONFIRMED · 원인 귀속 정정 | 공통 | 원안①은 **있음**(룰 파일) / **③+X17 안은 없음** |
| X11 | 매도 실패 복원이 **COMPLETED 슬롯을 POSITIONED 로** 되살릴 수 있음(두 경로 조건 비대칭) | B-9 | CONFIRMED · 도달성 추정 | 공통 | **없음** |
| X12 | 복원 유예가 **벽시계(09:05)·손절만** 커버 → **장중 재기동 0초**. 09-14 손절 43% 가 09:05:10~12 | C-N6 + B-W9 (M1) | CONFIRMED | 공통(**실전 P1**) | **있음(동작 변경) → 사전등록 + 결재** |
| X13 | **매도 후 재매수 쿨다운(`_sell_cooldowns` 30분)이 재기동에 소멸** | C-N5(신규분) | CONFIRMED | 공통(**실전 실질 P1**) | **있음(동작 변경) → 결재** |
| X14 | 원장 귀속 실패 매도 = **대금 2중 소멸** + DB 라벨 클래스명화 | C-N2 | CONFIRMED(**미발화**) | 페이퍼 | 없음 |
| X15 | `pending_sells_fallback.json` **데드레터** + 비원자적 `'w'` 덮어쓰기(09-08 사고 동형) | C-N3 | CONFIRMED(**미발화**) | 페이퍼 | 없음 |
| X16 | `strategy_for_sell = owner or self._strategy` 폴백 → **남의 전략 룰로 청산**(매 12초 루프) | B-W10 | CONFIRMED · **등급을 B-10 에서 이리로 이전** | 공통 | **있음 → 결재** |
| X17 | **`on_market_open`/`on_market_close` 가 8전략 중 1개에만 감** | **CR-1(신규)** | CONFIRMED(**로그 증명**) | 페이퍼(실전 무해) | **있음(관측치 변경) → 사전등록** |

### P3 (18건 · X6b 포함)

| # | 항목 | 출처 | 판정 |
|---|---|---|---|
| X18 | 후보 상한 인상이 `MAX_MANAGED_STOCKS=120` 을 건드림(조건부) | A-N2 | ~~P2~~ → **P3** |
| X19 | `candidate_stocks` 복원 owner 누락(`state_restorer.py:569` vs `:646` 비대칭) | A-N4 | ~~P2(실전)~~ → **P3**(시나리오 하향) |
| X20 | 후보 `name` = 종목코드 | A-N5 | CONFIRMED |
| X21 | 연속실패 경보 쓰로틀 없음(5회↑ 라운드마다) | A-N10 | CONFIRMED(잠복) |
| X22 | 속도제한 AIMD 부재 | A-N11 | CONFIRMED |
| X23 | `data_quality` 죽은 사슬(레포가 이미 주석 3곳에 문서화) | A-N9 | **신규 아님** |
| X24 | `MAX_NEW_ENTRIES_PER_CYCLE=3` 도달 불가(쿨다운 60 > 창 15) | B-2 | CONFIRMED |
| X25 | 같은 틱에 일봉 2회·한쪽만 미확정봉 드롭 | B-5 | CONFIRMED |
| X26 | `TradingStock.buy_cooldown_minutes` config 미배선 | B-6 | CONFIRMED |
| X27 | ~~EOD 청산 가드 fail-open(첫날 전량 청산)~~ → **극성만 문제 · 1전략 실전에선 도달 불가** | B-10 | **시나리오 REFUTED · 하향** |
| X28 | `가상 매도:` 로그 수익률 **100배 축소** | C-N4 | CONFIRMED |
| X29 | 「N/N 복원」 카운터가 전략 주입 미포함 | C-N7 | CONFIRMED |
| X30 | `_strategy_invested` 를 매도대금으로 차감(휴면) | C-N8 | CONFIRMED |
| X31 | 실전 원장 `fee_amount`/`net_profit`/`net_profit_rate` 미기입 | C-N9 | CONFIRMED |
| X32 | `is_test` 정보량 0 · `source` 는 DB명 상수 | C-N10 | CONFIRMED |
| X33 | `LIKE INCLUDING ALL` 이 **FK 미복사** | **CR-2(신규)** | CONFIRMED |
| X34 | 복리 사이징이 cost basis(미실현 미반영 · 전략별 최대 ±436,837) | C-W7 | 구조 판정 · DB 재현 |
| X6b | 다중 해시 시 상위 N 절단이 **해시 순** | A-N6 | CONFIRMED(잠복 · X5 와 한 묶음) |

**합계 — 신규 P1 3 · P2 14 · P3 18(X6b 포함) = 35건.** (기존 40건과 중복 0.)

---

## 5. 3층 권고 통합표

> **모든 항목은 «제안»이다. 이 검토로 바뀐 코드는 0줄이다.**
> 🔒 = 사장님 결재 필요 · 📋 = 사전등록 필요(관측치·실행시각 변경) · ✅ = 결재 불요(동작 0 변경)

### A. 지금 당장 — 동작 0 변경 · 1~2줄 · 그날 이득

| # | 조치 | 파일:줄 | 줄 수 | 닫는 결함 | 동결 충돌 | 승인 |
|---|---|---|---|---|---|---|
| **I1** | 급락/CB/국면 차단 로그에 `stock_code` + `_strategy_key` + 해석지수를 싣고 (종목,사유) **10분 쓰로틀** | `core/trading_context.py:355` (+`:334`, `:363`) | 1~3 | **X8** · 09-14 사전등록 P1·P2 「판정 불가」 | **없음**(로그만) | ✅ |
| **I2** | 3전략 캡 분기 **직전**에 10분 쓰로틀 INFO `[캡] {code} 평가 스킵 — 보유 N/M` | ma20 `strategy.py:142` · minervini `:157` · daytrading `:134` | 3 | **X3(P1)** | **없음**(룰 로직 무변경) | 📋 「계기 추가」로 사전등록 분리 권고 |
| **I3** | `{profit_rate:+.2f}%` → `{profit_rate*100:+.2f}%` | `db/repositories/trading.py:381` | 1 | X28 | 없음 | ✅ |
| **I4** | `_log_fund_sync_summary` 에 **`Σ by_owner == holding_restored` 단언**(불일치 ERROR) | `bot/state_restorer.py:768` | 1 | X29 · **2026-08-12 사고 유형** | 없음 | ✅ |
| **I5** | [C] 분봉 전략 경로에 `exit_timeframe != "intraday" → return` | `core/trading/position_monitor.py:341` | 1 | **X7**(A-N8 + B-7 **동시**) | 없음(8전략 전부 `daily` → **동작 0**) | ✅ |
| **I6** | 매도 실패 복원에 `state in (SELL_CANDIDATE, SELL_PENDING)` 조건 추가(실전 경로와 **대칭**) | `bot/trading_analyzer.py:443` | 1 | X11 | 없음 | ✅ |
| **I7** | `add_selected_stock` 실패를 **전략 단위로 집계**해 ERROR 1줄(어느 전략이 몇 칸 못 받았나) | `core/trading/order_execution.py:148-149` 부근 | 1~2 | X18 의 **유일한 가시 신호** | 없음 | ✅ |

> ❌ **A 층에 넣지 «않는» 것** — ~~「스냅샷 훅을 `to_thread` 로 내린다」~~. §3-1 R3 대로 **손절 감시 공백을 못 고친다.** 대신 **08:5x 장전 스냅샷 분리**를 B 층으로 올렸다(P1g).

### B. 실전 전환 전 — 필수 · 페이퍼 동작 0 또는 결재

| # | 조치 | 위치 | 줄 수 | 닫는 결함 | 동결 충돌 | 승인 |
|---|---|---|---|---|---|---|
| **P1a** | `reverse_confirm` 에 「예약/확정 이력 없으면 **no-op + ERROR**」 가드 + 취소실패 분기에서 `order.quantity` 대신 **`filled_quantity`** 사용 | `core/fund_manager.py:388` · `core/orders/order_timeout.py:278-284` · `core/orders/order_db_handler.py:151,193` | 2 + 2 | **X1(P1)** | 없음(실전 전용 경로) | ✅(페이퍼 영향 0) |
| **P1b** | `real_trading_records` + 인스턴스 표에 `UNIQUE(buy_record_id) WHERE action='SELL'` **마이그레이션**. 자식 생성 시 **FK 도 명시 생성** | DB + `db/repositories/trading.py:49-52` | 마이그레이션 1 | **X2(P1) · X33** | 없음 | 🔒(스키마 변경) |
| **P1c** | 복원 유예를 「09:05 이전」 → **「복원 완료 + M초」**로, **손절·max_hold·익절·전략신호 전부** 포함 | `core/trading/position_monitor.py:219-224` 및 `:227,:254,:314,:326,:339` | 1 + 4 | **X12** | **있음(동작 변경)** | 🔒 + 📋 |
| **P1d** | `_sell_cooldowns`·`_daily_realized_loss` 를 **거래일 키로 영속화**, 같은 거래일이면 승계 | `core/fund_manager.py:226, 236` | 소규모 | **X13** + 기존 **P2-18** | **있음(동작 변경)** | 🔒 |
| **P1e** | `enable_re_trading` 을 **config 로 빼고 값을 결정·명문화** + 타임아웃 복구 로그를 **WARNING + 경보** | `core/trading/order_execution.py:54, 478-486` | 2 | **X9** | 없음(실전 전용) | 🔒(값 결정) |
| **P1f** | 결재문에 **「실전 후보 출처 = 스크리너 스냅샷이 아니라 당일자 JSON/거래량 순위」** 명시 | 문서만 | 0 | §2 ① (a) 1-D | 없음 | 🔒(문구 승인) |
| **P1g** | 스냅샷 훅을 **08:5x 장전 1회**로 분리(09:00 엔 읽기만) | `bot/candidate_loader.py:55-61` · `bot/liquidation_handler.py:591-618` | 소규모 | 약점 ①-3(**34초 공백**) | **있음(실행 시각 변경)** | 📋 |
| **P1h** | `position_monitor.py:253` 의 `self._strategy` 폴백을 **「미해석이면 백스톱 전용, 전략 매도신호 스킵」**으로 | `core/trading/position_monitor.py:253, 339` | 1~2 | **X16** | **있음** | 🔒 |

> ❌ **B 층에서 «빼는» 것** — ~~B-10(EOD fail-open) 극성 반전~~. §3-1 R1 대로 **1전략 실전에서 도달 불가**다. 🔑 **이런 항목이 최소 집합에 남으면 진짜 P1(X1)의 우선순위를 갉아먹는다.**
> ⚠️ **기존 40건의 최소 집합**(자매 문서 §5 A1~A6 · B1~B5 · C1~C5)은 **그대로 유효**하다. 이 표는 그 위에 **추가**되는 것이다.

### C. 장기 리팩터 — 별도 결재

| # | 조치 | 닫는 결함 | 동결 충돌 | 승인 |
|---|---|---|---|---|
| **L1** | `params_hash` 를 「생성물을 결정하는 모든 입력」의 함수로 + `base_filter(self, universe, params)` 시그니처 통일 | X5 · X6b | 없음(스크리너 계층)이나 **해시가 바뀌면 과거 행과 단절** | 📋 필수 |
| **L2** | 후보 상한 상수 **1개로 통일** + `MAX_MANAGED_STOCKS` 와 **같은 결재**에 묶기 | X4 · X18 | 있음(후보 수 변경) | 🔒 |
| **L3** | `data_collector` 폴링을 **POSITIONED 로 좁히기**(라운드 12.2 → 약 7초, 추정) + **계기 3종**(라운드 소요·라운드당 호출·감시 지연) | X6 | 있음(관측치 변경) | 📋 |
| **L4** | 매도 판단을 **단일 결정자**로 통합([A]를 신호생성기로, 실행은 `ctx.sell` 한 경로) | X11 · X16 · 약점 ④-1/④-2 | 있음 | 🔒 |
| **L5** | **페이퍼도 `Order` 를 만들어** `pending → completed` 상태머신을 **매일 태우기**(⑤ 를 매일 검증) | 약점 ⑤-1 | 있음(큰 변경) | 🔒 |
| **L6** | 「자본」 정의 단일화(복리 사이징을 **mark-to-market** 으로) | X34 | **있음(사이징 변경) · 3전략 성과 계열 단절** | 🔒 |
| **L7** | `change_stock_state` 를 **전이 강제(위반 시 예외)**로 + 매수 멱등키 `(거래일, 종목, owner)` | 약점 ③-1 · X11 | 있음 | 🔒 |
| **L8** | `on_market_open`/`on_market_close` 를 **전 전략 루프**로 | X17 · X10 | 있음(관측치 변경) | 📋 |

---

## 6. 페이퍼 무사고가 증거인 범위와 아닌 범위

> **「5개월 페이퍼 무사고」는 판단 계층에 대해서는 유효한 증거이고, 주문 실행 계층에 대해서만 무효다.**
> C 의 「페이퍼는 ⑤ 에 대해 증거가 아니다」는 옳지만 **「페이퍼가 증거가 아니다」로 일반화하면 과장**이다(검수 §4-1).

### 증거 «있음» — 매일 도는 공통 경로 (파일 단위)

| 영역 | 파일 | 09-14 검증 근거 |
|---|---|---|
| 후보 선정·fail-closed | `core/candidate_selector.py` · `core/screener_snapshot_provider.py` · `runners/screener_snapshot_collector.py` | 106행 생성 → 56종목 소비, 폴백 0건 |
| 안전필터 | `core/candidate_selector.py:493-733` | 58 조회 → 56 통과, VI 2건 제외 |
| 급락/국면 게이트 | `core/trading_context.py:333-368` · `core/trading_decision_engine.py:222-225` | `ctx.buy` 차단 713회 · `auto` 축 발효 실증 |
| `ctx.buy` 가드 앞단·진입 밴드 | `core/trading_context.py:313-536` · `core/trading_decision_engine.py:409-418` | 밴드 거절 5건(`203650` 2,775 > 2,699) |
| 사이징 판단(페이퍼) | `core/virtual_trading_manager.py` `get_max_quantity` | `0015S0` 247주 @7,940 |
| 상태머신 전이 | `core/trading/stock_state_manager.py` | 전이 로그 정상, `[비정상 상태전이]` 0 |
| 복원·원장 리플레이 | `bot/state_restorer.py` · `core/virtual_trading_manager.py:367-475` | 36/36 · 리플레이 검산 ✅ |
| FM 예약/확정/회수 | `core/fund_manager.py`(**매도 측**) | EOD 정합성 통과 · 96원 격차 산식 재현 |
| EOD 스킵 판정 | `bot/liquidation_handler.py:157-270` | 33/33 스킵 |

### 증거 «없음» — 0회 실행 (파일 단위)

| 영역 | 파일 | 근거 |
|---|---|---|
| **OrderManager 상태머신** | `core/orders/order_base.py` · `order_manager.py` | `pending_orders` 0건 ×20 |
| **주문 수명주기·타임아웃** | `core/orders/order_timeout.py` | `타임아웃 복구` 0건 |
| **부분체결·취소·오탐복구** | `core/orders/order_monitor.py:121-223` | `주문 모니터링` 0건 |
| **실주문 발주** | `core/trading/order_executor.py` `place_buy_order`/`place_sell_order` | `매수 주문 시도` 0건 |
| **체결 콜백** | `core/orders/order_completion_handler.py` | `체결 콜백 수신` 0건 |
| **실전 owner 게이트** | `core/trading/order_executor.py:102-115` | 페이퍼는 이 분기를 안 탐 |
| **실전 전용 중복방지 5종** | `_active_buy_stocks` · `is_buying` · `can_add_position` · `is_sell_cooldown_active` · owner 게이트 | §2 ③ (d) 약점 ③-2 표 |
| **실전 원장 writer** | `core/orders/order_db_handler.py` · `db/repositories/trading.py:111-176` | `real_trading_rs_leader` **0행** |
| **FM 매수 측 연산** | `reserve_funds`/`confirm_order`/`add_position` | **무로그**라 페이퍼에서도 사후 검증 불가(약점 ⑤-4) |

> 🔑 **경계선 한 줄** — **`core/trading/order_execution.py:275`(페이퍼) 와 `:343`(실전) 사이가 그 경계다.** 왼쪽은 5개월 검증됐고, 오른쪽은 **세션 0회**다.
> 그리고 **경계를 넘는 순간 멱등성 보장이 «강함 → 없음»으로 바뀐다** — 페이퍼 매도만 DB 부분 유니크 인덱스를 갖고, 실전 표엔 **유니크가 0개**다(X2).

---

## 7. 미확정 질문 (다음 세션)

### 🥇 1순위 — 캡 오염 기간 특정 (X3)

**09-14 하루만 봤다.** `logs/robotrader_template_2026090*.log` · `2026091[01].log` 로 **같은 대조**(전략별 `[sync_positions] N` vs `config.yaml max_positions` vs `매수 시그널` 건수)를 돌려야 **3전략 고도화 계측의 오염 구간이 특정된다.** 이걸 안 하면 09-05·09-11 결정의 관측을 **되살릴 수 없다.**

### 그 밖의 미확정

| # | 질문 | 확정된 것 / 미확정인 것 |
|---|---|---|
| Q1 | **X1 의 브로커 응답 계약** — `tot_ccld_qty`/`rmn_qty`/`cncl_yn` 의 실제 값 | 확정: ①코드 경로 존재 ②`reverse_confirm` 무가드 ③판정식이 「취소 실패」 상태와 **정확히 일치**. **미확정: 실계좌 1회 조회로만 확정 가능.** |
| Q2 | **09:00:00~09:00:28 구간** | 08:40:37 다음 로그가 09:00:28 이라 **로그로 판정 불가**. `sleep(30)` 잔여로 설명 가능하다는 것까지만 확인. |
| Q3 | **X14·X15 도달성** | DB 클래스명 라벨 0건 · fallback 파일 부재로 **미발화만 확인**. **확률 미측정.** |
| Q4 | **경쟁 조건(약점 ④-1)** | 09-14 에 [B] 매도가 1건이라 **표본 0**. 단위 테스트 필요(실행 금지 원칙상 미수행). |
| Q5 | **X34 의 2026-07-29 결재문 원문** | **미대조**(C 도 같은 한계를 적었다). `_strategy_initial` 영구 10,000,000 이 의도인지 확인 필요. |
| Q6 | **X17 의 하류 전수** | `on_market_open`/`close` 에 의존하는 상태가 `daily_trades`/`daily_profit` 외에 더 있는지 **8전략 전수 확인 안 했다.** |
| Q7 | **실전 ⑤ 경로 런타임** | 09-14 로그에 체결 이벤트 0건이라 **코드 읽기로만** 판정. 확정은 **9/28 이후 소액 실주문 1건**으로만 가능. |
| Q8 | **`get_virtual_open_positions` 분모의 정확성** | 페이퍼엔 대사 상대가 없어 **「36 이 옳은지」 검증 불가.** |
| Q9 | **`real_trading_records.fee_amount` 를 채우던 «옛 writer»** | 레거시 224행은 전부 non-NULL 인데 현행 writer 는 안 쓴다. **어느 코드가 채웠는지 추적 안 했다**(X31). |
| Q10 | **X12 의 09:00~09:05 스킵 비용** | 그 구간 **가격 계기가 없어 측정 불가.** 측정하려면 「스킵 안 했으면 얼마였는지」 shadow INFO 가 필요(사전등록 대상). |

---

## 8. 출처 · 산출물

### 근거 자료

| 종류 | 경로 · 범위 |
|---|---|
| **로그** | `logs/robotrader_template_20260914_074007.log` (1,358,080 B · 9,244줄 · 07:40:07~18:34) — **상위집합**(`trading_20260914.log` 과 대칭차분 실측 0/130) |
| **DB** | `kis_template` (PostgreSQL 16 + TimescaleDB · 127.0.0.1:5433) — **SELECT 만.** `screener_snapshots` · `virtual_trading_records` · `paper_strategy_equity` · `paper_trading_state` · `real_trading_records` · `real_trading_rs_leader` · `pg_constraint` · `pg_indexes` |
| **코드** | 운영 디렉토리만 — `core/ bot/ framework/ api/ strategies/ config/ db/ utils/ runners/ collectors/ main.py`. 연구 코드(`scripts/ multiverse/ backtest/ archive/ lib/ books/ council/`)는 **근거에서 제외** |

### 산출물 (전부 `RoboTrader_template/scratchpad/real_trading_audit_20260914/`)

| 파일 | 내용 |
|---|---|
| `BRIEF2_pipeline_review.md` | 공통 브리프 · 절대 규칙 · 「이미 알려진 것」 |
| `review_A_candidates_data.md` | ①후보선정 ②데이터수집 (신규 N1~N11) |
| `review_B_entry_exit.md` | ③매수진입 ④매도진입 (신규 B-1~B-10 + W1~W10) |
| `review_C_fill_restore.md` | ⑤주문체결 ⑥재기동복원 (신규 N1~N11 + G1~G4 · W1~W10 · R1~R4) |
| **`CRITIC_verify2.md`** | **척추.** 32건 전수 판정 · 모순 3건 재조정 · 검수자 신규 2건 · 3층 권고 |
| `CRITIC_verify.md` §4 | 앞선 감사 40건 통합 목록 (중복 번호 참조용) |

### 자매 문서

- `docs/audit_2026-09-14_real_trading_switch.md` — **실전 전환 사전 감사**(6축 · 결함 40건 · P1 10건 · 최소 수정 집합 A/B/C/D). **이 문서는 그 위에 얹는 설계 검토**다.

### 관리자가 직접 확인한 것 (에이전트 인용의 2차 검증)

1. **DB 제약 실측**(`pg_constraint` + `pg_indexes`) — `real_trading_records` = PK + FK(`buy_record_id → id`) · **UNIQUE 0** / `real_trading_rs_leader` = **PK 만**(FK 0 · 시퀀스 공유) / `virtual_trading_records` = PK + FK + `idx_virtual_trading_unique_sell UNIQUE(buy_record_id) WHERE action='SELL' AND buy_record_id IS NOT NULL`.
2. **`bot/liquidation_handler.py:177-178, 265-266`** 폴백 = `owner or decision_engine.strategy` — **1전략 실전은 두 번째가 채워지므로 B-10 「첫날 15:00 전량 청산」은 성립하지 않는다**(검수 REFUTED 와 일치).

---

*(검토 종료. **코드 수정 0줄 · pytest 0회 · git 편집 0건 · DB 는 SELECT 만 · 로그는 읽기만.** 위 「수정안」은 전부 제안이며, 실행은 사장님 결재 후 별도 작업이다.)*
