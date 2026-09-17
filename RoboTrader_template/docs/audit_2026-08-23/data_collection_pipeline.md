# 데이터 수집 프로세스 전수 검수 (2026-08-23)

> 범위: kis-template(`RoboTrader_template`) 의 **모든 수집 경로**. 코드 수정 0줄 · 읽기 전용.
> 근거: 코드 독해(파일:라인) + `kis_template` DB SELECT + `logs/robotrader_template_2026082*.log`.
> 측정 기준일 = **2026-08-23(일)**. 최근 4거래일 = **8/18(화)·8/19(수)·8/20(목)·8/21(금)**
> (8/15 광복절·8/16 일·8/17 대체휴일 휴장 — 8/17 15:35 로그에 스킵 확인).

---

## §0 한줄 결론

**「수집이 도는가」는 대체로 정상인데 「무엇을 적재하는가」가 결함이다** — 라이브 일봉 쓰기 경로 2개가
전부 KIS **원주가**(`FID_ORG_ADJ_PRC="1"`)를 적재하는데, 저장 계약(`collectors/adj_repair.py:59` 「OHLC ← 조정 피드」, `price.py:116`)은
「`close` 는 이미 조정된 연속 시세」다. ⇒ **쓰기 경로가 저장 계약을 위반**한다.

> 🔎 **독립 검증(2026-08-23, 별도 verifier) — D1 정정**: 초안의 「close 가 «전부» 원주가」는 **REFUTED**. `adj_factor≠1` 100종목의 전이경계 104건 전수 판별 결과 **2026 이전 62:2 조정본(96.9%) · 2026 38:3 원주가(92.7%)** = **혼재(c)**. `035720` 2021-04 는 절벽 없이 연속(문서 반례 재현). 초안 8건 표본은 `effective_date` 가 `split_factor_infer`(2026~) 산출이라 **정의상 2026 만 뽑힌** 편향 표본. 🔴 초안이 제안한 「리더에서 `close/adj_factor`」는 74,938행 중 **35,180행(47%)을 새로 깨뜨린다** — 조치는 **쓰기 경로 수정 + 행별 선택 보정**(`adj_repair.py` 가 이미 그 설계)이어야 한다. 🔑 **오염의 메커니즘은 «구르는 장전 103봉 원주가 덮어쓰기»(D3)** — `003350`·`010120` 의 종목 내부 절벽이 마지막 장전 수집일의 정확히 101~104봉 전에 있다 ⇒ **D1 과 D3 는 한 결함**. 영향 분모 「100종목」도 과소 — 스탬프된 적 없는 `adj_factor=1/NULL` 불가능 점프 **218종목**(예 `060900` 345→7,530)이 밖에 있다. D2·D3·D4·단서 4건은 실측 정확. 소수 정정: D6 「5개 수급 수집기 전부」→ **4/5**(foreign_flow 는 `load_universe()`) · D11 분봉 8/18~21 로그-DB 는 4일 전부 **불일치**(8/13·14 만 일치) · credit 날짜 컬럼은 `deal_date` 가 아니라 **`date`** · `kis_market_api.py` 기본값 라인은 `:133`.

---

## §1 수집기 전수표

행 = 소스 · 열 = 트리거 / 적재경로 / 실패처리 / 최근 4거래일 실측 / 규약 / 판정

| # | 소스 | 트리거 | API → 테이블 (upsert 키) | 실패 처리 | 8/18·19·20·21 실측 | 규약 | 판정 |
|---|---|---|---|---|---|---|---|
| 1 | **daily** | EOD 15:35+ `system_monitor` → `_safe(collect_daily)` · 휴장일 전체 스킵 | KIS `FHKST03010100` output2 → `daily_prices` `(stock_code,date)` | `_safe` 가 예외만 `{"error":…}` 로. **종목별 실패는 세지도 않음**(`codes`=시도수) | **2,765행/일 전부 적재**(2,763종목 + 의사티커 2) · 로그 `rows` 19,392/19,388/19,385/19,386 | `date` **text** · `adj_factor` 미설정 · `updated_at=now()` | 🔴 |
| 2 | **daily_derived** | 1 안에서 매 EOD | `daily_prices` **전표** UPDATE (윈도우 함수) | 없음 | **3,158,409행 전부** `updated_at = 2026-08-21 15:xx` | — | 🔴 |
| 3 | **split_factor_infer** | 1 안(15:46) **+ corp_events 안(16:02)** — **하루 두 번** | `corp_events.meta` jsonb 병합 | 행별 try/except + rollback | 8/21 `183300`(x2 split)·`131100`(x5 merge) 2건 | `effective_date` = 갭 발생일 | 🔴 |
| 4 | **daily_adj** | 1 안, **3 의 «첫» 호출 직후에만** | `corp_events` → `daily_prices.adj_factor` UPDATE | 없음 | `adj` 124,847→124,950→125,053→**126,524** | `adj_close = raw_close / adj_factor` | 🔴 |
| 5 | **corp_action_watch** | 1 끝(15:46) | 탐지만 → `logs/corp_action_refetch_queue.jsonl` | 자체 try/except, 수집 비차단 | 미조정 의심 **247→249→252→251**건(신규 4/2/3/3) | — | 🟡 |
| 6 | **minute** | EOD `_safe(collect_minute)` | KIS 분봉 → `minute_candles` `(stock_code,datetime)` · DELETE+INSERT | `df` None/empty 면 `continue`(무기록) | 113,429/301 · 113,134/300 · 112,982/301 · 113,216/300 | `trade_date`·`date` 두 varchar 컬럼(같은 값) | 🟡 |
| 7 | **index** | EOD `_safe(collect_index)` — **`trade_date` 안 받음** | FDR `KS11/KQ11` → `index_daily` `(index_code,date)` | FDR 예외 → `_safe` | 8/13~8/21 **매일 2행** · 전체 48행/지수(06-15~08-21) | — | 🟢 |
| 8 | **regime index** | EOD, **`run_data_collection` «전»** 별도 훅 | FDR → `daily_prices` 의사티커 `KOSPI`/`KOSDAQ` | 3회 재시도 → 0행이면 WARNING | 8/21 `KOSPI 6934.91` · `KOSDAQ 803.23` 확인 | `adj_factor` NULL | 🟡 |
| 9 | **stock_market** | EOD `_safe(collect_stock_market)` — 인자 없음 | FDR StockListing → `stock_market` `(stock_code)` | **3층 검증 후 RuntimeError** — 유일한 fail-closed | 로그 KOSPI 942 / KOSDAQ 1821~1822 · 표 현재 **943 / 1824** | UPSERT 만, DELETE 없음 | 🟡 |
| 10 | **foreign_flow** | EOD `_safe(collect_foreign_flow)` | 네이버 `frgn.naver` 2p → `foreign_flow` `(stock_code,date)` | HTTP≠200·파싱실패 → **빈 df**(예외 없음) | **608종목/일** · max=**8/20**(T-1 정상) · 로그는 매일 `codes 2789 / rows 24320` | NaN → NULL | 🔴 |
| 11 | **corp_events** | EOD `_safe(collect_corp_events)` | OpenDART `list.json`(B·I) → `corp_events` | status≠000 WARNING 후 break · 절단 시 WARNING | 신규 15/13/13/16건, status=000 | `event_date`=공시일(PK 불변) | 🟢 |
| 12 | **investor_trend** | EOD + **신선도 게이트(≥5일)** | KIS `FHKST01010900` → `investor_trend_daily` | 3회 재시도 · None=실패 / 빈 df=해당없음 **구분** | **8/19 만** 실행(2,763/2,763, 82,810행) · max = **08-19** | — | 🟡 |
| 13 | **program_trade** | 동일 게이트 | KIS `FHPPG04650201` → `program_trade_daily` | 동일 | **8/19 만**(2,763, 82,810행) · max = **08-19** | `raw` jsonb 원문 보존 | 🟡 |
| 14 | **short_sale** | 동일 게이트(60일 구간 TR) | KIS `FHPST04830000` → `short_sale_daily` | 동일 | **8/19 만**(2,763, 113,112행) · max = **08-19** | 동일 | 🟡 |
| 15 | **credit_balance** | 동일 게이트 — **4/4일 전부 발화** | KIS → `credit_balance_daily` (날짜필드 `deal_date`) | 동일 | **매일** 80,993/81,000/81,006/81,012행 · max = **08-18** | 동일 | 🟡 |
| 16 | **overtime** | 동일 게이트 | KIS → `overtime_daily` | 동일 | **8/19 만**(2,763, 82,810행) · max = **08-19** | 동일 | 🟡 |
| 17 | **장전 일봉 덮어쓰기** | **07:40~09:01 · 매일 78~80종목** (종목 추가 훅) | KIS `FHKST03010100` **원주가** → `daily_prices` | 조회 실패 시 종목 제거 + ERROR | 80 / 80 / 78 / 80건 · **휴장 8/17 에도 42건** | `updated_at`·`adj_factor`·`trading_value` 미설정 | 🔴 |
| 18 | **post_market_data_saver** | 장마감 훅 — **로그상 발화 0건** | KIS **수정주가(`adj_prc="0"`)** → `daily_prices` | — | `일봉 데이터 저장 시작` 로그 **0건** | 1·17 과 **반대 규약** | ⬜ 죽은 경로 |
| 19 | **뉴스** | **별도 레포 `D:\GIT\NewsQuant`** · Task Scheduler `\RoboTrader_AutoStart` 07:40 → `run_all_robotraders.bat` [4/5] | 5소스 → `news` / `collection_log` | `collection_log.status` 기록 | 마지막 8/21 19:23 · 8/21 실적재 dart 780·naver 166·hankyung 92·mk 35 | `news_stock` 은 DB 트리거로 파생 | 🟡 |
| 20 | **DART 재무** | **없음** | — | — | `dart_financials_asfiled` 17,892행/2,556종목 · `created_at` **전부 2026-08-08 13:51~17:11** | PK `(stock_code,bsns_year)` = PIT 파괴 | 🔴 |
| 21 | **adj_repair** | **미배선** | — | — | 프로덕션 import 0건 | — | ⬜ |

---

## §2 소스별 상세 (파일:라인 증거)

### 2-1 오케스트레이터 · 트리거

- 진입점은 하나뿐이다 — `bot/system_monitor.py:323` `await self._run_data_collection(current_time)`
  → `bot/system_monitor.py:621` `asyncio.to_thread(run_data_collection, trade_date)`
  → `collectors/eod_collection.py:45`. `main.py`·`.bat`·스케줄러가 수집기를 직접 부르는 경로는 없다.
- **휴장일 게이트 = `bot/system_monitor.py:260-271`** — `is_holiday(current_time)` 이면 EOD 후속 **전체** 스킵.
  실측: `2026-08-17 15:35:02 | 휴장일(2026-08-17 광복절 대체 휴일) — EOD 후속 작업 전체 스킵`.
- **단계 격리 = `collectors/eod_collection.py:37-42` `_safe`** — 예외를 `{"error": ...}` 로 바꿔 ERROR 1줄만 남긴다.
  🔑 이 격리는 **예외에만** 걸린다. 「예외 없는 0행」은 그대로 통과한다.
- 실행 순서/소요(8/21 실측): 15:46 daily 끝 → 15:48 stock_market → 16:02 corp_events → 16:10 credit → 16:10:55 완료.

### 2-2 daily — 원주가 적재

`collectors/daily_collector.py:64` 가 `adj_prc` 를 **넘기지 않는다**:

    df = kis_market_api.get_inquire_daily_itemchartprice(output_dv="2", div_code="J", itm_no=code)

기본값은 `api/kis_market_api.py:134` 의 `adj_prc: str = "1"` 이고, 같은 파일 `:150` 주석이
`# 0:수정주가, 1:원주가` 라고 스스로 밝힌다. ⇒ **원주가**.

- `collectors/daily_collector.py:85` `rows[-lookback_days:]`(기본 7) → 매일 **최근 7봉만** UPSERT.
- `collectors/daily_writer.py:45-49` `ON CONFLICT (stock_code,date) DO UPDATE SET open/high/low/close/volume...`
- **정지 패딩 행의 생성 지점이 바로 이 UPSERT 다.** KIS 가 거래정지일에 「전일 종가 4값 + `volume=0`」 봉을
  주는데 `parse_kis_daily_row`(`collectors/daily_writer.py:20-37`)는 `close>0` 만 보므로 그대로 통과한다.
  실측: OHLC 4값 동일 ∧ `volume=0` 행이 8/18 **129** · 8/19 **128** · 8/20 **132** · 8/21 **137**건이고,
  같은 날짜의 `volume=0` 행수와 **정확히 일치**한다 — volume=0 행은 전부 4값 고정 패딩이다.

### 2-3 daily_derived — 전표 재도장

`collectors/daily_collector.py:98` → `collectors/daily_derived.py:55-64`:

    UPDATE daily_prices dp SET returns_1d=..., updated_at = CURRENT_TIMESTAMP
    FROM vol_calc vc WHERE dp.stock_code=vc.stock_code AND dp.date=vc.date

WHERE 절에 날짜 제한이 **없다**. 실측 `SELECT date_trunc('day',updated_at), count(*) ... GROUP BY 1`
결과가 **단 한 행** — `2026-08-21 | 3158409`(시각까지 보면 전부 15시대).
⇒ **`updated_at` 은 변경 추적에 쓸 수 없다.** 메모리 단서 재검증 완료(행수는 3,155,643 → **3,158,409** 로 갱신).

### 2-4 split_factor / adj_factor — 이중 호출 + 하루 지연

`infer_and_stamp_split_factors` 를 부르는 곳이 **둘**이다:

- `collectors/daily_collector.py:101` (`update_adj_factors` **직전**)
- `collectors/corp_events_collector.py:25` import → corp_events 수집 끝에서 재호출

8/21 로그가 그대로 증언한다:

    15:46:22 collectors.split_factor_infer | split_factor 스탬프: 183300 split ... 권리락일=2026-08-21 x2 direction=split
    16:02:13 collectors.split_factor_infer | split_factor 스탬프: 131100 split ... 권리락일=2026-08-21 x5 direction=merge
    16:02:13 collectors.corp_events_collector | [corp_events] ... 신규=16 스탬프=1
    16:10:55 bot.system_monitor | EOD ... 일봉 {... 'split_factor_stamped': 1 ...}

⇒ **메모리의 「`split_factor_stamped` 0→1 자동 발화, 종목 미확인」은 `183300`(액면분할 2:1) 이다.**
그리고 같은 날 **두 번째 스탬프 `131100` 이 있었는데 EOD 요약 일봉 dict 에는 안 나온다**(별도 로그 줄에만).

**그래서 생긴 결함**: `update_adj_factors` 는 `collect_daily` 안에서만(15:46) 돈다.
16:02 스탬프는 그날 `adj_factor` 로 **반영되지 않는다**. DB 가 확인해 준다:

| 종목 | 스탬프 시각 | 권리락 전 close | 권리락일 close | `adj_factor`(권리락 전) |
|---|---|---|---|---|
| `183300` (x2 분할) | 15:46 · daily 경로 | 54,400 | 27,700 | **2** ✅ |
| `131100` (x5 병합) | 16:02 · corp_events 경로 | 450 | 2,280 | **NULL** 🔴 |

`131100` 의 올바른 값은 `1/5 = 0.2` 인데 8/23 현재까지 미반영이다(다음 EOD = 8/24 에 반영될 것).

### 2-5 「close 는 조정본」이라는 문서와 데이터의 정면 충돌 — 최상위 결함

`corp_events` 에서 `effective_date` 가 확정된 **8건 전부**를 실측했다:

| 종목 | 권리락일 | 배수 | 방향 | 직전 close | 권리락 close | 저장 `adj_factor` |
|---|---|---|---|---|---|---|
| 003350 | 2026-04-20 | 5 | split | 48,200 | 9,400 | 5 |
| 001130 | 2026-05-18 | 11 | (NULL) | 156,500 | 14,300 | 11 |
| 336060 | 2026-08-06 | 5 | merge | 590 | 2,985 | 0.2 |
| 369370 | 2026-08-07 | 5 | merge | 750 | 3,800 | 0.2 |
| 054940 | 2026-08-12 | 5 | merge | 760 | 3,815 | 0.2 |
| 031860 | 2026-08-14 | 10 | merge | 693 | 6,930 | 0.1 |
| 183300 | 2026-08-21 | 2 | split | 54,400 | 27,700 | 2 |
| 131100 | 2026-08-21 | 5 | merge | 450 | 2,280 | **NULL** |

**8/8 전부 무보정 절벽이다** — 단 8건은 전부 2026년 라이브 수집분(검증 정정: 표본 편향). `48,200 / 5 = 9,640 ≈ 9,400` — **이 구간의** `close` 는 원주가다. ⚠️「연속 시세를 얻으려면 일괄 `close / adj_factor`」는 **틀렸다**(2026 이전 96.9% 가 이미 조정본이라 일괄 나누기는 35,180행을 깨뜨린다). `003350` 은 한 종목 안에서도 규약이 갈린다(2026-03-13 9,660 → 03-16 45,900 ×4.75, 거래량은 감소 = 장전 103봉 덮어쓰기 경계).

그런데 소비자 층은 반대로 적혀 있다:

- `db/repositories/price.py:116` — 「**close 는 이미 조정 저장**(`adj_close = raw_close / adj_factor`)인데 volume 은 원본이라...」
- `db/repositories/price.py:129` · `db/quant_daily_reader.py:158` — `(volume * COALESCE(adj_factor,1))` 만 하고 **close 는 손대지 않는다**
- `CLAUDE.md` — 「가격에 `adj_factor` 를 곱하지 말 것 — 이미 분할조정된 연속 시세다」

프로덕션 전역 grep 결과 **`close / adj_factor` 를 하는 라이브 코드는 0건**
(히트는 `archive/`·주석·`scripts/` 뿐).

⇒ 「곱하지 말 것」은 맞다. 「이미 조정본」은 **2026 이전엔 참, 2026 라이브 수집 구간(장전 103봉 창이 지나간 자리)에선 거짓**이다(검증 정정). 해법은 «나누기»가 아니라 **쓰기 경로를 저장 계약(조정본)에 맞추고 행별로 보정**하는 것.
영향 규모: `adj_factor IS NOT NULL AND <> 1` = 74,938행 / 100종목 중 **원주가 구간은 40종목 39,758행**; 그 밖에 스탬프 안 된 불가능 점프 **262건/227종목**(패딩 직후 219건 제외 시 43건/29종목), 그중 218종목은 `adj_factor` 가 끝까지 1/NULL.
별도로 `adj_factor IS NULL` = **370,976행 / 2,678종목**(읽기 계층이 `COALESCE(...,1)` 로 삼키므로
volume 은 안전하나, 스탬프 미반영 종목이 여기 숨는다).

### 2-6 장전 일봉 덮어쓰기 — 메모리 단서 「09:00 ~103봉」의 정체

경로:
`core/intraday_stock_manager.py:132` 및 `:138-141`
→ `core/intraday/data_collector.py:46 collect_daily_data_only`
→ `core/intraday/data_collector.py:67 self.broker.get_ohlcv_data(stock_code, "D", 150)`
→ `core/intraday/data_collector.py:87 _save_daily_to_db` → `:104`
→ `db/repositories/price.py:94-104` `INSERT INTO daily_prices ... ON CONFLICT DO UPDATE SET open/high/low/close/volume`.

조정 여부: `days=150 → int(150*0.7)=105 > 100` 이므로 `api/kis_api_manager.py:357` 의
`get_inquire_daily_itemchartprice_extended(...)` 분기를 탄다. `adj_prc` 를 안 넘기므로
`api/kis_market_api.py:170` 기본값 `adj_prc="1"` = **원주가**.

실측 규모/시각 — 「09:00」이 아니라 **07:40~09:01** 이고 **매일 78~80종목**:

| 날짜 | `일봉 데이터 수집 완료` | `DB 저장 완료` | 첫 줄 | 마지막 줄 |
|---|---|---|---|---|
| 8/18 | 80 | 80 | 07:40:12 | 09:00:40 |
| 8/19 | 80 | 80 | 07:40:12 | 09:01:07 |
| 8/20 | 78 | 78 | 07:40:11 | 09:01:05 |
| 8/21 | 80 | 80 | 07:40:11 | 09:01:08 |

로그 본문의 봉 수는 `101개`(8/18) → `102개`(8/19) → `103개`(8/20·8/21) 로 증가 중이다.

🔴 **이 경로는 휴장일 게이트 밖이다** — 2026-08-17(대체휴일)에도 `일봉 데이터 DB 저장 완료` **42건**.
이 UPSERT 는 `updated_at`·`adj_factor`·`trading_value`·`market_cap` 을 건드리지 않는다
(`db/repositories/price.py:95-104` 컬럼 목록에 없음).

### 2-7 규약이 반대인 세 번째 쓰기 경로 (현재 죽어 있음)

`core/post_market_data_saver.py:112-120` 은 **`adj_prc="0"`(수정주가)** 로 100일치를 받아
같은 `save_daily_prices_batch` 로 **같은 행**에 UPSERT 한다. 즉 라이브 쓰기 3경로 중
**2개는 원주가, 1개는 수정주가**이고 마지막에 쓴 쪽이 이긴다.
현재는 무해하다 — 트리거 `core/intraday/realtime_updater.py:397-407` 의
`장 마감 데이터 저장 시작`·`일봉 데이터 저장 시작` 로그가 **8월 전체 로그에서 0건**이다.
**발화하면 즉시 규약 혼입이 된다.**

### 2-8 foreign_flow — 조용한 78% 결손

- `collectors/foreign_flow_fetcher.py:51-53` — HTTP≠200 이면 `logger.warning` 후 `break`,
  최종 `:105-106` 에서 **빈 DataFrame**. 파싱 실패(`:77-78`)도 같다. **예외가 안 난다.**
- `collectors/foreign_flow_collector.py:45` `return {"codes": len(codes), "rows": total}` — `codes` 는 **시도 수**.
- 실측 충돌:
  - 로그(4일 전부 동일): `외국인수급 {'codes': 2789, 'rows': 24320}`
  - DB: `foreign_flow` 는 8/13·14·18·19·20 각각 **608종목**뿐, 전 기간 distinct 종목도 **627**.
- `24,320 / 608 = 40.0` — 성공한 608종목이 각각 40행(2페이지)이고 **나머지 2,181종목은 0행**이다.
- `bot/system_monitor.py` 의 승격 가드는 `rows == 0` 만 ERROR 로 올린다 —
  **부분 결손은 원리적으로 못 잡는다.**

### 2-9 수급 5축 — 신선도 게이트의 두 얼굴

게이트: `collectors/investor_trend_collector.py:147-158` — `STALE_DAYS=5`,
`gap = date.today() - max(date)`, `gap >= 5` 일 때만 실행.

**(가) 4축은 톱니로 T-2 결손 중.** 8/19 에만 발화 → `investor_trend_daily`·`program_trade_daily`·
`short_sale_daily`·`overtime_daily` 의 **max = 2026-08-19**. 마지막 거래일은 8/21 이므로
**8/20·8/21 이 비어 있다.** 다만 TR 이 30거래일 창을 주므로 8/24 발화 시 메워진다 —
`program_trade_daily` 가 2026-07-03~08-19 사이 **결손 없음**(7/17 제외, 휴장 추정)인 것이
그 복구가 실제로 동작한다는 증거다.

**(나) credit 은 게이트가 구조적으로 항상 참이다 = 죽은 게이트.**
공급이 늦어 `max(date)` 가 `date.today()` 를 절대 따라잡지 못한다. 4/4일 전부 발화했고
트리거 문구가 `최신 2026-08-12 · 6일` → `08-12 · 7일` → `08-13 · 7일` → `08-14 · 7일` 로
**매일 하루씩만 전진**한다. 현재 `credit_balance_daily` max = **2026-08-18**.
비용: 매일 2,763종목 API 콜 + 약 9분(16:02 → 16:11).

**(다) 유니버스 기준일이 하드코딩돼 있다** — `collectors/investor_trend_collector.py:133`

    def universe(conn, as_of: str = "2026-08-14") -> list[str]:

5개 수급 수집기가 **전부** 이 함수를 쓴다(`collectors/market_flow_collector.py:35-37`, `:124`).
⇒ 2026-08-14 이후 신규 상장은 영구 제외되고, 그날 행이 사라지면
`codes=[]` → 「성공 0/0」으로 조용히 통과한다.

🟢 잘 된 점: `with_retry`(`collectors/investor_trend_collector.py:50-69`)가
**`None`(진짜 실패)과 빈 df(해당없음)를 구분**한다. 실측이 그 설계를 지지한다 —
credit 의 `해당없음 55` 는 4일간 안정적이고 `실패 0` 이다.

### 2-10 stock_market — 유일한 fail-closed, 단 래칭

- `collectors/stock_market_collector.py:99-111` 0건·교집합 → `RuntimeError`,
  `:42-77` 시장별 규모하한 80% → `RuntimeError`. **한 행도 안 쓰고** 죽는다.
  전 수집기 중 유일하게 부분응답을 막는다.
- 래칭 실측: 로그는 `KOSPI 942 · KOSDAQ 1821~1822` 를 쓰는데 표는 **KOSPI 943 · KOSDAQ 1824**
  (`updated_at` max = `2026-08-21 15:48:57`). UPSERT 가 상폐를 지우지 않아 기준선이 단조 증가한다
  (`collectors/stock_market_writer.py:7-12`, 코드 주석 `collectors/stock_market_collector.py:56-60` 이 이미 인지).

### 2-11 corp_events

- `collectors/corp_events_collector.py:41` `DART_PBLNTF_TYPES = ("B","I")` — 분할·병합(I) 포함 확인.
- 실측 8/18~8/21 매일 `status=000`, 신규 15/13/13/16건.
  8/21 까지 `rights_issue`·`split`·`bonus_issue` 적재가 이어진다.
- `split` 197건 중 `split_factor` 보유 **113**, `effective_date` 보유 **8**.

### 2-12 corp_action_watch — 탐지만, 4일간 조치 0

`collectors/daily_collector.py:107-111` 에서 예외 격리 호출. 로그:

    8/18 미조정 의심 247건(신규 4 큐) / 8/19 249(신규 2) / 8/20 252(신규 3) / 8/21 251(신규 3)

WARNING 으로 매일 나가지만 재수집은 **의도적으로 실행하지 않는다**
(`collectors/corp_action_watch.py:22-26`). 큐 파일 `logs/corp_action_refetch_queue.jsonl`.

### 2-13 뉴스 — 이 레포에 없다

- 실체: **`D:\GIT\NewsQuant`**(별도 git 원격). `news_scraper/database.py:376` 이 `collection_log` 에 INSERT,
  `:99`·`:137` 이 `news`·`collection_log` 를 생성. `config.yaml` 이 **port 5433 · name `kis_template`** 를 가리킨다
  (2026-08-16 전환, 롤백본 `config.yaml.bak.20260816-newsquant`).
- 기동: Windows Task Scheduler `\RoboTrader_AutoStart`(주간 07:40, 마지막 실행 2026-08-21 07:40)
  → `D:\GIT\run_all_robotraders.bat` [4/5] `NewsQuant\start.bat`, [5/5] 가 트레이딩 봇.
  **한 스케줄·두 콘솔** — 이것이 「별도 프로세스」의 정체다.
- `news_stock` 은 NewsQuant 가 아니라 **kis_template 쪽 DB 트리거**가 만든다
  (`scratchpad/news_pipeline_20260816/10_create_trigger.sql`, gitignore 라 grep 에 안 잡혔다).
- 상태 실측: `collection_log` 마지막 2026-08-21 19:23. `naver_finance`·`hankyung`·`mk_news` **셋 다**
  `status=success` 인데 `error_message='타임아웃 후 회수'`.
  🔑 **그런데 실제 적재는 되고 있다** — `news` 8/21: dart 780 · naver_finance 166 · hankyung 92 · mk_news 35.
  ⇒ 「회수 패치는 발효 중이고 타임아웃 자체는 매 사이클 그대로」라는 기존 판정이 재확인된다.
- 🔴 트레이딩 봇은 `news`·`news_stock` 을 **한 줄도 읽지 않는다**(운영 디렉토리 grep 0건).

### 2-14 DART 재무 — 갱신 수집기가 「없다」 (재검증 완료)

- `dart_financials_asfiled` 실측: **17,892행 / 2,556종목**,
  `created_at` 전부 **2026-08-08 13:51:31 ~ 17:11:39**. 단일 배치 확정.
- 적재 스크립트는 `scripts/discovery/fundamental_risk_filter/f4_load.py` 인데
  **미머지 브랜치 `feat/fundamental-risk-filter-pit` 에만 있고 디스크에도 없다**
  (`git merge-base --is-ancestor` 부정, `git ls-tree main` 0건).
- `financial_statements` 에 **INSERT 문이 레포 전역 0건** — 유일한 변경은 수동 단일컬럼 UPDATE
  (`scripts/backfill_operating_cash_flow.py:339`, `IS NULL` 가드라 정정공시 반영 불가).
- `api/kis_financial_api.py` 432줄 — **DB 쓰기 0줄**, 소비자는 비활성 예제전략(`sawkami`·`lynch`)뿐.
- 🔴 `scripts/backfill_operating_cash_flow.py:241-274` — 네트워크 예외·HTTP 오류·**DART 쿼터 초과(`status=020`)**가
  전부 같은 `"not_found"` 로 떨어지고 로그가 DEBUG 라, 쿼터로 통째 실패한 실행이
  「DART 에 데이터가 없음」으로 보고된다. 같은 상황을 `scripts/dart_industry_c1_collect.py:92-93` 은
  `RuntimeError` 로 올린다 — **같은 레포 안에서 처리가 갈린다.**
- 문서 모순: `docs/DATA_MANAGEMENT.md:62,96-101,116` 과 `SYSTEM_FLOW.md:108-111,299,306` 이
  **존재하지 않는 08:30 재무 수집기**를 기술한다(인용된 `core/data_collector.py` 에 재무 코드 0줄,
  SQL 은 `INSERT OR IGNORE` = SQLite 문법).
- 쓰기 대상 DB 규약 위반 2건: `scripts/dart_industry_c2_load.py:82`·`scripts/dart_mcap_b4_load.py:58` 이
  `database="kis_template"` 를 하드코딩한다(`CLAUDE.md` 의 `require_explicit_target_db` 규칙 위반).
  `scripts/backfill_operating_cash_flow.py:109` 만 준수.

---

## §3 체계적 발견 (여러 소스에 공통인 패턴)

**① 「시도 수」를 「성공 수」로 보고하는 관용구가 절반의 수집기에 퍼져 있다.**
`{"codes": len(codes), ...}` — daily(`collectors/daily_collector.py:112`) ·
minute(`collectors/minute_collector.py:41`) · foreign_flow(`collectors/foreign_flow_collector.py:45`).
이 셋은 종목별 실패를 **세지도 않는다**. 반대로 수급 5축은 `ok/fail/no_data` 를 갈라 세고
`failed_codes` 까지 남긴다(`collectors/investor_trend_collector.py:194-197`).
**같은 EOD 안에 두 문화가 공존한다** — 그래서 「성공 로그」의 뜻이 소스마다 다르다.

**② `_safe` 는 예외만 잡는다 — 「예외 없는 0행」은 전부 통과한다.**
`collectors/eod_collection.py:37-42`. foreign_flow 의 2,181종목 결손이 정확히 이 틈으로 들어온다.
`bot/system_monitor.py` 가 나중에 붙인 승격 가드도 `rows == 0` 이라는 **전부 아니면 전무** 조건이라
부분 결손을 원리적으로 못 잡는다.

**③ 「가드가 재는 양이 상수면 그건 가드가 아니다」의 새 사례 — credit 신선도 게이트.**
공급 지연 > 임계값이면 `stale` 은 항상 참이다(4/4일 발화 실측).
그런데 **똑같은 게이트가 나머지 4축에는 너무 잘 걸려** 상시 T-2~T-5 결손을 만든다.
🔑 ***하나의 임계값이 소스마다 정반대 방향으로 고장난다*** — 소스별 공급 지연을 안 재고 공통 상수를 쓴 결과다.

**④ 같은 테이블을 세 경로가 서로 다른 규약으로 쓴다.**
`daily_prices` 쓰기 = EOD(원주가·7봉) / 장전(원주가·103봉·**휴장일 무시**) / post_market(수정주가·100봉·죽음).
게다가 `daily_derived` 가 매일 전표 `updated_at` 을 재도장해
**누가 언제 무엇을 썼는지 추적이 원리적으로 불가능**하다.

**⑤ 같은 함수를 두 오케스트레이션 단계가 각자 부른다.**
`infer_and_stamp_split_factors` 가 daily(15:46)·corp_events(16:02) 두 번 도는데,
그 결과를 소비하는 `update_adj_factors` 는 **첫 번째 뒤에만** 있다 ⇒ 두 번째 스탬프는 하루 늦는다.
🔑 *「두 번 부르면 멱등이니 안전하다」가 참이려면 소비자도 두 번 돌아야 한다.*

**⑥ 문서·주석이 데이터와 반대인 지점이 3곳이고, 셋 다 코드를 읽으면 즉시 반증된다.**
`db/repositories/price.py:116`(close 조정본) · `docs/DATA_MANAGEMENT.md §1.2`(08:30 재무) ·
`SYSTEM_FLOW.md:108-111`(재무 수집 단계).

**⑦ 「예외 없이 빈 결과」를 만드는 fetcher 가 두 종류다.**
네이버(`collectors/foreign_flow_fetcher.py:51-53`, `:101-103`)와
DART OCF(`scripts/backfill_operating_cash_flow.py:241-274`)가 **HTTP 오류·쿼터 초과·파싱 실패를
전부 「데이터 없음」으로 접는다.** 반대로 `scripts/dart_industry_c1_collect.py:92-93` 과
`collectors/investor_trend_collector.py:50-69` 는 둘을 구분한다 — 같은 레포에 두 규범이 있다.

---

## §4 결함 후보 (심각도 · 영향받는 소비자 · 결정은 사장님 몫)

### D1 🔴🔴 `daily_prices.close` 규약이 «혼재» — 2026 라이브 쓰기 경로가 저장 계약(조정본)을 위반한다(원인 = D3 장전 덮어쓰기) — 라이브 + 전 백테스트

- 증거: `api/kis_market_api.py:134`·`:170`(기본 `adj_prc="1"`) · `collectors/daily_collector.py:64` ·
  `core/intraday/data_collector.py:67` · 분할 8건 **8/8 절벽**(§2-5 표) ·
  프로덕션에 `close / adj_factor` **0건**.
- 영향: `db/repositories/price.py:get_daily_prices` 와 `db/quant_daily_reader.py` 를 읽는 **모든 것** —
  라이브 8전략 · regime 게이트 · 개념축 백테스트 전부. 원주가 구간 **40종목 39,758행**(+ 스탬프 안 된 218종목)에서 가격이 배수만큼 틀리고,
  이동평균·수익률·변동성은 절벽 이후 20~260봉 동안 오염된다. 🔴 **일괄 `close/adj_factor` 는 금지** — 이미 조정본인 60종목 35,180행을 깨뜨린다.
- 🔑 이것은 「곱하지 말라」와 **다른 문제**다. 기존 규칙(곱하지 말 것)은 여전히 맞다. 빠진 것은 **나누기**다.
- ✅ 검증에서 **측정했고 답은 «아니다»**: 과거 구간(2026 이전)은 96.9% 조정본. 원주가는 2026 라이브 수집 구간에 국한. 선행 문헌 `collectors/adj_repair.py:144`(08-20)·`plans/2026-06-23-phaseA2a-daily-collector.md:14`(원주가 적재가 «의도된 결정»이었음 — 06-22 문서와 정반대) 참조.

### D2 🔴 foreign_flow 가 78% 결손을 성공으로 보고

- 증거: 로그 `codes 2789 / rows 24320`(4일 동일) vs DB **608종목/일**, 전 기간 627종목.
- 영향: 수급 축을 쓰는 모든 스크리너·연구.
  「627종목뿐」이라는 기존 인식은 맞았지만, **그것이 실패의 결과라는 사실이 로그에 안 보인다**는 게 결함이다.
- 미규명: 2,181종목이 네이버에서 왜 0행인지(차단 vs 페이지 부재)는 재지 않았다.

### D3 🔴 장전 일봉 덮어쓰기가 휴장일에도 돌고, 원주가 103봉을 밀어 넣는다

- 증거: §2-6. 휴장 8/17 에 42건.
- 영향: 매일 78~80종목 × ~103봉 ≈ **8,000행/일**이 원주가로 재기입된다.
  그날 후보에 든 종목이 분할 이력을 가지면 절벽이 매일 다시 찍힌다
  (8/21 후보에 실제로 `054940` = 8/12 5:1 병합 종목이 들어 있다).
- 부수 효과: **백테스트가 「살아 있는 표」를 읽는다** — 같은 스크립트가 실행 시각에 따라 다른 답을 낸다.

### D4 🔴 DART 재무 갱신 경로 부재 + 문서는 있다고 말함

- 증거: §2-14. `dart_financials_asfiled` 단일 배치 2026-08-08, 적재 코드는 미머지 브랜치에만.
- 영향: 재무 축을 배선하면 **굳은 스냅샷**을 읽는다.
  문서를 근거로 설계하면 존재하지 않는 08:30 수집기를 가정하게 된다.

### D5 🟡 split_factor 이중 스탬프 → `adj_factor` 하루 지연 (`131100` 현재 NULL)

- 증거: §2-4. 8/21 16:02 스탬프분이 8/23 현재까지 미반영.
- 영향: 권리락 당일 밤 ~ 다음 EOD 사이 그 종목의 `adj_factor` 가 틀리다. 지금은 **≤1거래일** 이지만,
  D1 을 고쳐 close 를 나누기 시작하면 이 창이 곧바로 **가격 오류**가 된다.

### D6 🟡 수급 유니버스 기준일 하드코딩 `as_of="2026-08-14"`

- 증거: `collectors/investor_trend_collector.py:133`, 소비 5곳.
- 영향: 신규 상장 영구 제외. 그 날짜 행이 사라지면 **「성공 0/0」으로 조용히 통과**한다.

### D7 🟡 credit 신선도 게이트가 구조적으로 항상 참 (죽은 게이트)

- 증거: §2-9(나). 4/4일 발화, 트리거 문구가 하루씩만 전진.
- 영향: 매일 2,763콜 · 9분 소모. 더 나쁜 것은 게이트의 존재가 「제어되고 있다」는 착시를 준다는 점이다.

### D8 🟡 나머지 수급 4축은 상시 T-2~T-5 결손 (현재 8/20·8/21 비어 있음)

- 증거: max = 2026-08-19, 마지막 거래일 8/21.
- 완화 근거: `program_trade_daily` 2026-07-03~08-19 무결손 → 30일 창 복구가 실제로 동작한다.
- 결정 사항: **장중에 이 표를 읽는 소비자가 있다면 최대 5일 낡은 값을 본다.**

### D9 🟡 `post_market_data_saver` 가 반대 규약(`adj_prc="0"`)으로 잠들어 있다

- 증거: `core/post_market_data_saver.py:112-120` · 트리거 로그 발화 0건.
- 영향: 지금은 무해. 되살아나면 **한 종목 시계열 안에 원주가와 수정주가가 섞인다.**

### D10 🟡 `updated_at` 전표 재도장 (3,158,409행/일)

- 증거: §2-3. 변경 추적·증분 소비 불가. 검증은 백업 `batch_id` 로만 가능하다.

### D11 🟡 minute_candles 8/13·8/14 로그-DB 불일치 (미규명)

- 로그 EOD: `codes 300 / rows 113,503`(8/13), `300 / 113,185`(8/14).
- DB: **364종목 / 135,837행**(8/13), **364 / 135,276**(8/14). 8/18~8/21 은 300~301종목으로 일치한다.
- `minute_candles` 쓰기 경로는 `collectors/minute_writer.py` **하나뿐**이고 `replace_minute_day` 는
  종목 단위 DELETE 라 **다른 실행이 합집합으로 남는다**. 그 다른 실행의 흔적을 봇 로그에서 찾지 못했다.

### D12 🟡 stock_market 규모하한 래칭

- 표 943/1824 vs 수집 942/1822. 이탈률 3.2%/년 기준 수년 뒤 정상 수집이 영구 거부된다
  (코드 주석 `collectors/stock_market_collector.py:56-60` 이 이미 인지하고 있다).

---

## §5 한계 (못 본 것 · 권한 거부)

1. **권한 거부 0건.** `kis_template` 의 대상 표는 전부 SELECT 에 성공했다.
   이 문서에서 「0행」이라고 쓴 것은 전부 **실제 0행**이지 권한 문제가 아니다.
2. **D1 의 과거 구간 범위 미측정.** 분할 8건이 전부 절벽인 것은 확인했으나,
   2021~2025 구간의 `close` 가 원주가인지, 과거 백필 시점의 조정본인지는 **재지 않았다**.
   `corp_action_watch` 가 매일 세는 「미조정 의심 251건」이 상한의 힌트지만 정의가 동일하지 않다.
3. **D11 미규명.** 8/13·8/14 의 추가 64종목이 어느 실행에서 왔는지 못 찾았다
   (수동 `python -m collectors.minute_collector` 는 print 만 하므로 봇 로그에 남지 않는다).
4. **`_MAX_PAGES` 절단·DART `status != 000` 이 최근 4일에 실제로 났는지**는 WARNING 0건으로만 확인했다.
   ⚠️ `robotrader_template_*.log` 는 콘솔 캡처라 블록 버퍼링된다 — 유실 가능성을 배제하지 못한다.
5. **NewsQuant 내부는 이 레포 밖**이라 코드 라인 검증을 대행 조사로 받았다.
   `news_scraper/scheduler.py` 가 **미커밋 수정 상태**라는 보고가 있는데 직접 확인하지 않았다.
6. **8/22(토)·8/23(일)은 휴장**이라 실측 대상이 아니다. 최근 4거래일 = 8/18·19·20·21 로 잡았다.
7. **실행 검증 없음.** 라이브 트리에서 pytest·스모크·수집기 실행 금지 지침을 지켰다 —
   전부 코드 독해 + DB SELECT + 로그 grep 이다. 「이렇게 동작할 것이다」가 아니라
   「이렇게 동작했다」만 적으려 했으나, 미래 동작(예: 8/24 수급 복구)은 추정임을 표시했다.
