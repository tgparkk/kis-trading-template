# 지수 일봉 소스 KIS 전환 + 신선도 경보 — 설계 (2026-09-10)

> 사장님 결정(2026-09-10): **(c) 신선도 경보** + **(b) 지수 일봉 소스를 KIS API 로 전환**, 롤백 스위치 1개.
> 근거 증거: `scratchpad/eod_20260909/UPSTREAM_fdr_probe.md` · `scratchpad/eod_20260909/LANE_B_data.md` §1.
> 라이브 매매는 어느 쪽이든 **불변**이다 — 장중 시장방향 필터는 KIS 실시간을 따로 쓴다.
> 구현은 워크트리 `D:/tmp/kis-wt-index-kis`(브랜치 `feat/index-kis-freshness`, base `65c91a5`)에서 한다.

---

## 1. 현행 데이터 흐름 — 두 경로가 «따로» 돈다

| 경로 | 코드 | 대상 표 | 실행 시각(실측) | 반환 계기 |
|---|---|---|---|---|
| **W-idx1** EOD 지수 수집 | `collectors/index_collector.py:27-37` → `collectors/index_writer.py:27-32` | `index_daily` | T 15:49 (`index_daily.created_at` 09-07 = `15:49:11`) | `{'KOSPI':6,'KOSDAQ':6}` |
| **W-idx2** regime 지수 갱신 | `core/regime/index_refresh.py:45-87` → `db/repositories/price.py:64` | `daily_prices` 의사티커 `KOSPI`/`KOSDAQ` | T 07:40 · T 15:35 (`daily_prices.created_at` 09-07 = `15:35:05`) | `{'KOSPI':6,'KOSDAQ':6}` |

- 둘 다 `fdr.DataReader('KS11'/'KQ11', today−10일)` 를 호출한다(`index_collector.py:30,34` · `index_refresh.py:57,67`).
- 둘 다 **FDR 이 돌려준 행 수**를 그대로 성공 계기로 쓴다(`index_collector.py:36` 은 `upsert_index_rows` 의 `len(rows)`, `index_refresh.py:79` 는 `len(daily)`).
- EOD 오케스트레이터 `collectors/eod_collection.py:51` 은 `_safe(collect_index)` 로 감싸는데, `_safe`(`:39-44`)는 **예외만** 잡는다. FDR 이 옛 봉 6개를 «정상 반환»하면 `error` 키가 없어 경보가 없다 ⇒ **fail-silent**.
- 결과: `index_daily`·`daily_prices` 의사티커 max(date) 가 **2026-09-07 에서 2거래일 멈췄는데 로그·EOD 요약은 전부 정상**이었다.

### 1-1. 소비자

| 소비자 | 읽는 곳 | 근거 |
|---|---|---|
| 국면 게이트 `RegimeGate` | `daily_prices` 의사티커 종가 | `core/regime/regime_gate.py:8,37,91` (`_INDEX_LOOKBACK_DAYS=400`, `:34`) |
| EOD 벤치마크 «에포크 종가» | `daily_prices` 의사티커 | `bot/eod_benchmark.py:241-260` (`fetch_epoch_close`) |
| EOD 벤치마크 «현재 지수» | **KIS 실시간** `inquire-index-price`(`FHPUP02100000`) | `bot/eod_benchmark.py:222-236` → `api/kis_market_api.py:402-413` · 호출 `:298-299` (`"0001"`/`"1001"`) |
| 백테스트·섹터 동조 검정 | `index_daily` | `scratchpad/comove/s08_idxcheck.py:13` · `backtest/concept_fidelity_audit/backtest_vs_live.py:74` |

⇒ **벤치마크 한 줄만 이미 KIS 를 쓰고 있어서 맞았다.** 어긋난 쪽은 DB 뿐이다(LANE_B §1-6).

### 1-2. 표 스키마 (실측 `\d`)

- `index_daily(index_code varchar NOT NULL, date **text** NOT NULL, open/high/low/close/volume double precision, created_at timestamp DEFAULT now())` · PK `(index_code, date)` · **`updated_at` 컬럼이 없다** ⇒ 「오늘 UPSERT 됐는지」를 원리적으로 관측 못 한다.
- `daily_prices(stock_code, date **text**, open/high/low/close, volume bigint, …, adj_factor double precision, created_at, updated_at)` · PK `(stock_code, date)`.
- **의사티커 4종 실측**: `KOSPI` 1,392행(2021-01-04~2026-09-07) · `KOSDAQ` 1,392행(동일) · `KS11` 601행(2024-01-02~**2026-07-08 동결**) · `KQ11` 601행(동결).
- `adj_factor`: `KOSPI`/`KOSDAQ` 는 **전행 NULL**, `KS11`/`KQ11` 는 1. 읽기 계층이 `COALESCE(adj_factor,1)` 로 흡수한다(`db/repositories/price.py:161` · `db/quant_daily_reader.py:158`).

### 1-3. 🔑 지금까지 「T 봉」이 언제 들어왔나 (오해 방지)

`daily_prices` 의사티커 T 행의 `created_at` 은 **T 당일 15:35:0x** 이다(09-01~09-07 5개 전부). 즉 FDR 은 T 15:35 에 이미 T 확정 종가를 줬다(09-07 KOSPI 6995.39 = 확정값). **T+1 07:40 에 들어오는 게 아니다.** 전환 후에도 이 시각 계약은 유지되어야 한다.

---

## 2. KIS 일봉 지수 API — **프로브로 확정됨 (2026-09-10)**

> 🔴 **초안 정정**: 초안이 가정한 URL `inquire-daily-indexchart` 는 **이 서버에 없다**(HTTP 404 · 본문 빈 문자열). 아래는 프로브 **실측**이다 → `scratchpad/index_kis_probe/RESULT.md`.

- 선택: **국내업종 기간별시세(일/주/월/년)** · URL **`/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice`**(주식기간별시세와 **같은 URL**, 시장구분만 `J`→`U`) · tr_id **`FHKUP03500100`**.
  - 대안 B `inquire-index-daily-price`(`FHPUP02120000`)도 200 이지만 **「기준일부터 100봉」**이라 창 제어가 안 된다 ⇒ 날짜 범위를 받는 위 경로를 쓴다(10일 창 · `--start` 백필이 자연스럽다).
- 래퍼: `api/kis_market_api.py` 의 `get_index_daily_chart()` — 기존 `get_inquire_daily_itemchartprice`(`:132-165`)와 **같은 형태**.
- 요청 파라미터(**실측 200**): `FID_COND_MRKT_DIV_CODE="U"` · `FID_INPUT_ISCD="0001"`/`"1001"` · `FID_INPUT_DATE_1`/`FID_INPUT_DATE_2`=`YYYYMMDD` · `FID_PERIOD_DIV_CODE="D"` · `FID_ORG_ADJ_PRC="0"`(업종엔 무의미하나 인자 형식상 전달).
- 응답 필드(**확정** · `output2`): `stck_bsop_date`(`YYYYMMDD`) · `bstp_nmix_oprc` · `bstp_nmix_hgpr` · `bstp_nmix_lwpr` · `bstp_nmix_prpr` · `acml_vol`. 🔑 **날짜는 `stck_` 접두사, 가격은 `bstp_` 접두사로 섞여 있다** — 추측 배선이 금지였던 이유가 이것이다.
- 🔑 **거래량 단위 = 천 주**: 09-07 KOSPI `acml_vol` 240,446 vs FDR/DB 240,446,154 ⇒ 저장 시 **`int(acml_vol) * 1000`**(반올림 오차 ≤ 999주). §12 결정 2 해소.

### 2-1. 프로브 — **완료 (2026-09-10 01:0x KST)**

`scratchpad/index_kis_probe/` (읽기 전용 · 호출 7회 · DB 쓰기 0 · 라이브 로그 오염 0). 결과 전문 → **`scratchpad/index_kis_probe/RESULT.md`**.
합격 기준 4개 **전부 충족**: ①키 6개 확정 ②09-07 KOSPI 종가 6995.39 = DB 값, `|Δ| = 0` ③09-08(6954.52)·09-09(7051.64) 봉 **있음** ④거래량 비율 기록(천 주).
⚠️ KOSDAQ(`1001`)은 프로브에서 A 경로(404)만 시도했다 — **같은 API 형식이라는 전제는 「예상」**이고, 첫 라이브 실행의 `index_daily` KOSDAQ 행으로 확인한다(§10 P1).

---

## 3. 소스 선택 설계

```python
# config/constants.py
INDEX_DAILY_SOURCE = "kis"      # "kis" | "fdr"
```

- **KIS 우선 · FDR 폴백은 「KIS 가 장애일 때」만.** 🔑 **「장애」에는 «예외»뿐 아니라 «`None` 반환»도 포함된다** — `api/kis_auth.py` 의 `_url_fetch` 는 404 에 예외를 던지지 않고 **DEBUG 한 줄만 남기고 `None`** 을 준다(프로브 실측). 이걸 장애로 접지 않으면 경로가 통째로 없어져도 조용하다. KIS 가 «빈 결과»를 준 건 폴백 사유가 **아니다** — 빈 결과는 판정 대상이지 장애가 아니고, 폴백하면 지금 상류가 죽어 있는 FDR 이 «옛 6봉»을 정상처럼 돌려줘 fail-silent 가 그대로 재현된다(§1).
- 🔴 **신선도 검사는 스위치 «밖»에 있다** — `"fdr"` 로 롤백해도 검사는 돈다. 이 결함을 잡았어야 할 장치를 롤백이 같이 꺼버리면 안 된다.
- 신선도 판정은 **실제로 쓴 소스**에 붙는다. 결과 dict·로그·reconcile 행에 `src`(`kis`/`fdr`)를 같이 남긴다.
- KIS 경로는 호출 직전 `auth()` 로 방어한다(`collectors/market_flow_collector.py:122` 와 동일 패턴). 실패는 예외 → 폴백 → 신선도 경보.

---

## 4. 신선도 경보 — 축 2개를 «따로» 판정한다

### 4-1. 기준일 `D_ref` (달력·휴장일 문제를 데이터로 푼다)

```
today  = now_kst().date()
cutoff = today            if now_kst().time() >= 15:40   else today - 1일
D_ref  = max(date) FROM daily_prices
         WHERE stock_code IN INDEX_FRESHNESS_ORACLE_CODES AND date <= cutoff
```

- `INDEX_FRESHNESS_ORACLE_CODES = ("005930","000660","035420")` — PK 앞자리를 타서 즉시 응답(전표 `max(date)` 는 3백만 행 스캔이라 안 쓴다). 실측 3종목 전부 max=2026-09-09.
- 🔴 **`cutoff` 가 «반드시» 필요한 이유(실측)**: 장전 W1 훅이 **T 당일 07:40:1x 에 T 행을 73~78종목 넣는다**(09-08 78건 · 09-09 73건, `created_at` 최소 `07:40:12`; W1 계약은 `config/constants.py:26-33`). `cutoff` 없이 `max(date)` 를 쓰면 07:40 에 `D_ref=T` 가 되어 **정상인 지수(T−1)가 매일 아침 STALE 로 오탐**한다.
- 각 호출 시점의 기대값: 07:40 → `D_ref=T−1`(지수도 T−1, PASS) · 15:35 → `D_ref=T−1`(KIS 가 T 를 쓰면 T ≥ T−1, PASS) · 15:49 → `D_ref=T`(`collect_daily` 가 1단계로 이미 씀 ⇒ **지수도 T 여야 한다 — 이번 결함을 잡는 지점**) · 휴장일/주말 → `D_ref` = 직전 거래일(PASS).

### 4-2. 두 축

| 축 | 판정 | 잡는 것 | 못 잡는 것 |
|---|---|---|---|
| **A. 상대** | `max(index date) < D_ref` → STALE | 지수만 밀린 경우(= 이번 결함) | 일봉 파이프라인이 «같이» 멈춘 경우(`D_ref` 도 같이 멈춘다) |
| **B. 절대** | `today − max(index date) > INDEX_FRESHNESS_MAX_CALENDAR_LAG`(=5일) | A 의 사각 + 오라클 3종목이 전부 밀린 경우 | 5일 미만의 짧은 결손 |

**두 축은 한 줄에 합치지 않고 따로 찍는다**(2026-09-08 교훈: 「한 규칙의 두 축은 따로 판정한다」).

### 4-3. 표면

- 로그(각 표·각 지수 1줄, `logger.warning`, 태그 고정):
  `[index-freshness] STALE axis=A table=index_daily index=KOSPI max=2026-09-07 ref=2026-09-09 lag=2 src=kis`
- EOD 요약: `collect_index` 반환 dict 에 `src`·`stale` 를 **추가**한다 → `지수 {'KOSPI': 6, 'KOSDAQ': 6, 'src': 'kis', 'stale': []}`.
  `bot/system_monitor.py:653,662` 은 이 값을 f-string 으로 흘릴 뿐이라 **`bot/` 는 한 줄도 안 고친다**.
- ERROR 승격은 **하지 않는다**. EOD 판정이 ERROR **집합 차분**으로 돌아가는데(2026-09-08 EOD) 상류가 죽어 있는 동안 매일 같은 ERROR 가 쌓이면 그 판정이 무뎌진다. 판정 기록은 아래 reconcile 행이 맡는다. ⬜ 사장님이 원하면 승격은 1줄 추가로 가능(§12 결정 1).

### 4-4. `collection_reconciliation` 행 — **넣는다** (dataset='index')

2026-08-17 에 지운 `reconcile_index` 는 「새 DB vs **죽은 레거시 DB**」 교차비교였고, 제거 사유는 **비교 대상이 도달 불가가 된 것**이지 「지수 판정이 불필요」가 아니다(`collectors/index_collector.py:7-10` — 같은 주석이 *표는 유지한다*고 명시). 지금 넣으려는 것은 sector/financials 와 같은 **자기완결 건강 판정**이다(`collectors/sector_collector.py:957-978` · `collectors/sector_writer.py:654-673`).

- 🔴 **부활 금지 심볼과 이름이 겹치면 안 된다** — `tests/collectors/test_index_collector.py:25-28` 이 `reconcile_index`·`reconcile_verdict`·`_LEGACY_CODE_MAP` 재유입을 막고 있다. 새 함수명은 **`check_index_freshness`**(그 가드 테스트는 그대로 둔다).
- 컬럼 매핑: `trade_date` = ISO `YYYY-MM-DD`(sector/financials 규약. minute 의 `YYYYMMDD` 와 섞지 않는다) · `real_rows` = 소스가 준 행 수(옛 「6」) · **`new_rows` = 직전 max(date) 보다 «뒤»인 행 수**(= 「N행 갱신 ≠ 최신성」을 표에서 갈라놓는 칸) · `overlap` = `real_rows − new_rows` · `coverage` = 신선한 지수 비율(0.0/0.5/1.0) · `value_match_rate` = **NULL**(대조할 2차 소스가 없다 — 가짜 숫자를 넣지 않는다) · `verdict` = `PASS`/`FAIL`.
- 기존 `dataset='index'` 8행(2026-06-26~07-07)과 PK 충돌 없음(날짜 서로소).

---

## 5. 결손 봉(09-08·09-09) 백필

- 첫 KIS 실행의 **10일 달력 창**(`index_collector.py:30` · `index_refresh.py:25`)이 그대로 메운다 — 첫 실행이 **2026-09-18 이전**이면 09-08 이 창 안이다. 그 뒤로 밀리면 `--start` 로 1회 지정한다(`index_collector.py:42`, `refresh_regime_indices(start=...)`).
- 🔑 **겹침 6일(09-01~09-07)은 UPSERT 로 KIS 값이 FDR 값을 덮는다**(`index_writer.py:6-8` · `db/repositories/price.py:64-77` 의 W3 는 `past_rows_insert_only=False` 가 «의도»). 그래서 첫 실행 «전»에 §2-1 프로브로 종가 일치를 먼저 확인한다. **거래량 단위는 별개 축**이다 — 소비자가 없는 칸이지만 단위가 바뀌면 조용한 불연속이므로 프로브에서 비율을 기록하고 §12 결정 2 로 올린다.
- 검증 SQL(첫 EOD 이후 1회, 읽기 전용):

```sql
SELECT index_code, max(date), count(*) FROM index_daily GROUP BY 1;
SELECT stock_code, max(date), count(*) FROM daily_prices
 WHERE stock_code IN ('KOSPI','KOSDAQ') GROUP BY 1;
SELECT stock_code, date, close FROM daily_prices
 WHERE stock_code IN ('KOSPI','KOSDAQ') AND date IN ('2026-09-08','2026-09-09') ORDER BY 1,2;
SELECT * FROM collection_reconciliation WHERE dataset='index' ORDER BY trade_date DESC LIMIT 3;
```

---

## 6. 07:40 regime 경로

- 토큰은 **있다** — 같은 프로세스가 07:40:12 에 이미 KIS 로 일봉을 받아 쓰고 있다(§4-1 W1 실측). 인증은 봇 기동 시 `framework/broker.py:221`.
- 07:40 의 KIS 조회는 T 가 아직 안 끝났으므로 **T−1 까지**가 정상이다 ⇒ `D_ref=T−1` 과 일치(PASS). 「행이 적다」로 경보하지 않는다.
- 장전 throttle(멱등 스킵·백오프·일일 캡, `bot/system_monitor.py:505-572`)은 **그대로 둔다** — 2026-06-29 FDR 폭격(23,908회) 재발 방지 장치이고 KIS 에도 같은 예산 논리가 필요하다. 멱등 스킵(`_regime_indices_present_for`, `:576-597`)은 「오늘자 행이 이미 있으면 호출 안 함」이라 **전환 후 07:40 에는 대개 스킵되지 않는다**(T 행은 아직 없다) — 현행과 동일.

---

## 7. 실패 모드

| # | 상황 | 설계된 거동 |
|---|---|---|
| F1 | 07:40 KIS 토큰 없음/만료 | `auth()` 실패 → 예외 → FDR 폴백(현재는 죽어 있음) → **축 A 발화**. `_url_fetch` 는 EGW00123 자동 재발급을 이미 갖고 있다(`api/kis_auth.py:461-470`) |
| F2 | 15:35 에 **가마감 봉**을 받는다 | 그대로 쓴다(막지 않는다). **T+1 07:40 의 10일 창이 UPSERT 로 자가치유**한다. 게이트는 어차피 당일 봉을 버린다(`regime_gate.py:53-63`). 🔑 첫 라이브일에 15:35 기록값과 16:18 벤치마크 값(`bot/eod_benchmark.py:298`)을 **대조해 관측만** 한다 — 가드는 안 단다(2026-09-08 사장님 방침) |
| F3 | 휴장일·주말 | `D_ref` 가 직전 거래일이라 PASS. 별도 달력 불필요 |
| F4 | KIS 가 빈 `output2` | 폴백 **안 한다**(§3) → 0행 → 축 A 발화 |
| F5 | 워크트리에 `.env` 없음 | 테스트는 KIS·FDR 둘 다 **모킹**한다. CLI 단독 실행은 auth 실패로 폴백 후 경보 |
| F6 | 오라클 3종목이 전부 밀림 | 축 A 는 무음 → **축 B 가 잡는다**(§4-2) |
| F7 | KIS 가 100건 상한으로 잘림 | 10일 창이면 최대 7봉이라 무관. `--start` 로 긴 창을 줄 때만 연속조회가 필요 — 이번 범위 밖(하면 `kis_market_api.py:167-230` 패턴) |

---

## 8. 롤백

`config/constants.py` 의 **`INDEX_DAILY_SOURCE = "kis"` → `"fdr"` 한 줄.** (`W1_PAST_ROWS_INSERT_ONLY`(`config/constants.py:34`)와 같은 형식 — 주석에 롤백 문구를 같은 형식으로 붙인다.)
⚠️ 롤백은 **이미 쓰인 데이터를 되돌리지 않는다**. 그리고 §3 대로 **신선도 검사는 롤백해도 계속 돈다**.

---

## 9. 바꾸면 «안 되는» 것

1. `index_daily`·`daily_prices` **스키마**(컬럼 추가·타입 변경·`updated_at` 신설 전부 금지).
2. 의사티커 이름 `KOSPI`/`KOSDAQ`. `KS11`/`KQ11`(601행·2026-07-08 동결)은 **읽지도 쓰지도 지우지도 않는다**.
3. `adj_factor` 규약 — 의사티커는 NULL 유지, 가격에 곱하지 않는다, 거래량 조정은 읽기 계층에만(`db/repositories/price.py:148-161`).
4. `run_data_collection` 반환 dict 의 **`"reconcile"` 빈 키**(`collectors/eod_collection.py:74-76` — `system_monitor` 계약) · EOD 단계 «순서».
5. `tests/collectors/test_index_collector.py:25-28` 의 부활 금지 가드.
6. 장전 throttle 상수 · `regime_gate` 읽기 경로 · `bot/eod_benchmark.py` 전체.
7. DB명 하드코딩 금지 — 새 읽기는 기존 연결(`KisDbConnection` / `price_repo`)만 쓰고 새 DSN 을 만들지 않는다.

---

## 10. 사전등록 예측 (첫 라이브 EOD 이후 판정)

| # | 예측 | 반증 |
|---|---|---|
| P1 | `index_daily` max(date) = 그날 거래일, `index_code` 2개 모두 | 하나라도 T 미만 |
| P2 | `daily_prices` KOSPI·KOSDAQ max(date) = 그날 거래일 | 위와 동일 |
| P3 | 09-08 종가 KOSPI ≈ **6,955** · KOSDAQ ≈ **812** / 09-09 KOSPI ≈ **7,052** · KOSDAQ ≈ **830** (16:18 벤치마크 줄 실측, 정수 반올림 ⇒ 허용 ±1) | 벗어나면 소스 불일치 |
| P4 | 행 수: `index_daily` 59 + (신규 거래일 수) · `daily_prices` 의사티커 1,392 + (동일) — **두 표의 증가분이 같다** | 증가분 불일치 |
| P5 | 겹침 6일(09-01~09-07) 종가는 **변하지 않는다**(KIS = FDR, `|Δ| ≤ 0.01`) | 값이 바뀌면 §2-1 프로브 미이행 |
| P6 | EOD 벤치마크 한 줄의 지수 레벨·당일 %는 **불변**(이미 KIS 실시간) | 바뀌면 `fetch_index_snapshot` 을 건드린 것 |
| P7 | `[index-freshness]` 발화 **0건**(정상일) · `collection_reconciliation(dataset='index')` verdict = `PASS`, `new_rows` = 신규 거래일 수 | |
| P8 | 07:40 에 오탐 STALE **0건** (§4-1 cutoff 검증) | 아침마다 발화하면 cutoff 미적용 |
| P9 | 라이브 3표(`virtual_trading_records`·`paper_strategy_equity`·포지션) **불변** · 매매 판단 로그 차분 0 | |

---

## 11. 머지·배포 타이밍

- 🔴 **머지는 09:00~15:30 KST «밖»에서만.** 라이브 트리 장중 브랜치 전환 금지 · 라이브 트리에서 테스트/스모크 실행 금지.
- 회귀 게이트는 **09:10 KST 이후**에만 돌린다.
- 기준선 = `D:/tmp/main_baseline_failures_20260907.txt` (**15줄**, 실측 확인). 판정은 실패 **집합의 양방향 차분**(새로 생긴 것 / 사라진 것 둘 다 0).
- 머지는 `--no-ff`, 커밋 메시지는 파일/히어도큰으로, push 후 `gh api repos/<o>/<r>/commits/<sha> --jq .author.login` 이 `null` 이 아닌지 확인.

---

## 12. 사장님 결정 대기

1. **ERROR 승격 여부** — 현행 설계는 WARNING + reconcile 행. `bot/system_monitor.py` 에 1줄 추가하면 ERROR 로 올릴 수 있으나 EOD 의 ERROR 집합 차분 판정이 둔해진다(§4-3).
2. ~~**거래량 단위**~~ — ✅ **해소(2026-09-10)**: KIS 는 **천 주** 단위 ⇒ `int(acml_vol) * 1000` 으로 기존 단위를 잇는다(오차 ≤ 999주 · 소비자 0). 구현·단위 테스트 반영 완료.
3. ~~**프로브 실행 승인**~~ — ✅ **완료**. §2·§2-1 이 실측으로 갱신됐다.

---

## 13. 구현 노트 — 설계와 «달라진 것» (2026-09-10 · 브랜치 `feat/index-kis-freshness`)

| # | 설계 | 구현 | 이유 |
|---|---|---|---|
| D1 | URL `inquire-daily-indexchart` | `inquire-daily-itemchartprice` + `FID_COND_MRKT_DIV_CODE="U"` | 초안 URL 이 **404**(§2) |
| D2 | 「KIS 가 예외면 폴백」 | 예외 **또는 `None` 반환**이면 폴백 | `_url_fetch` 는 404 에 None 을 준다(§3) |
| D3 | `check_index_freshness` 위치 미지정 | `collectors/index_writer.py` 에 두고 두 경로가 같이 쓴다 | `collect_index` 는 conn, regime 는 `price_repo` 로 «날짜만» 넘기면 판정 로직이 하나로 유지된다 |
| D4 | regime 경로 이음매 `fdr=` | `kis=` 이음매를 나란히 추가 | 테스트가 네트워크를 안 타게 (`.env` 없는 워크트리) |
| D5 | — | `_max_date_from_repo` 가 **(읽었나, 최신일)** 2튜플 | 「못 읽었다」와 「행이 없다」를 구분하지 않으면 조회 실패가 곧 STALE 이 되어 경보가 자기 고장으로 운다 |
| D6 | — | 오라클 조회는 **cutoff 이하로 «집계 전»에 자른다** | max 만 뽑아 뒤에서 자르면 07:40 에 D_ref 가 `none` 이 되어 판정이 통째로 사라진다(구현 중 실측) |
| D7 | 폴백 단위 미지정 | `collect_index` 는 **경로 통째로**, regime 는 **지수별** | 전자는 `src` 가 스칼라 1개, 후자는 기존 「한 지수 실패 격리」 계약이 있다 |
