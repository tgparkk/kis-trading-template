# 계획 — 지수 일봉 KIS 전환 + 신선도 경보 (2026-09-10)

> 설계: [`docs/superpowers/specs/2026-09-10-index-kis-freshness-design.md`](../specs/2026-09-10-index-kis-freshness-design.md)
> 워크트리 `D:/tmp/kis-wt-index-kis` · 브랜치 `feat/index-kis-freshness` · base `main 65c91a5`
> 🔴 라이브 트리(`D:/GIT/kis-trading-template`)에서 **pytest·봇 스크립트 실행 금지** · 장중(09:00~15:30) 브랜치 전환 금지
> 🔴 워크트리에 `.env` 가 없다 ⇒ **모든 테스트는 KIS·FDR 를 모킹**한다. 네트워크·DB 를 타는 테스트는 만들지 않는다.
> **목표 변경 파일 5개**(운영): `config/constants.py` · `api/kis_market_api.py` · `collectors/index_writer.py` · `collectors/index_collector.py` · `core/regime/index_refresh.py`. 리팩터 금지.

---

## Task 0 — 프로브로 KIS 응답 필드 «실측» — ✅ **완료 (2026-09-10 01:0x KST)**

> 결과 전문 → `scratchpad/index_kis_probe/RESULT.md`. 🔴 **초안 URL `inquire-daily-indexchart` 는 404** ⇒ 확정 경로는 `inquire-daily-itemchartprice` + `FID_COND_MRKT_DIV_CODE="U"` + `FHKUP03500100`. 필드 6개 확정 · 09-07 |Δ|=0 · 09-08·09-09 봉 있음 · `acml_vol` = **천 주**.

**왜 먼저인가**: `FHKUP03500100` 의 `output2` 키 이름이 repo 3곳 어디에도 없다(설계 §2). 추측 배선은 금지.

- 새 파일(연구용, 운영 아님): `scratchpad/index_kis_probe/probe_kis_indexchart.py`
- 실행: **라이브 venv · 1회 · 읽기 전용 · 09:00~15:30 밖**. DB 쓰기 0, 파일 쓰기 0(표준출력만).
- 내용: `from api.kis_auth import auth`(패턴 = `collectors/market_flow_collector.py:109,122`) → `kis._url_fetch('/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice', 'FHKUP03500100', '', params)` 를 `"0001"`·`"1001"` 2회. **(초안의 `inquire-daily-indexchart` 는 404 — 정정본이 이것이다.)**
- 인쇄: ① `output2[0]` 의 **전체 키 목록** ② 최근 5봉 원문 ③ 09-01~09-07 종가를 `index_daily` 저장값과 대조 ④ 09-08·09-09 봉 유무 ⑤ `acml_vol` / 저장 `volume` 비율.

**수용 기준**
- [ ] 일자·시가·고가·저가·종가·거래량 6개 키 이름이 확정됐다.
- [ ] 09-07 KOSPI 종가와 DB `6995.39` 의 `|Δ| ≤ 0.01`.
- [ ] 09-08·09-09 봉이 응답에 **있다**(없으면 (b) 전환 자체를 재검토 → 사장님 보고).
- [ ] 거래량 비율을 기록했다(설계 §12 결정 2 입력).

---

## Task 1 — 상수 + 순수 신선도 평가기 (테스트 먼저)

**파일**
- `config/constants.py` — `W1_PAST_ROWS_INSERT_ONLY`(`:22-34`) **바로 아래**에 같은 형식으로 블록 추가:
  `INDEX_DAILY_SOURCE = "kis"` · `INDEX_DAILY_SOURCES = ("kis","fdr")` · `INDEX_FRESHNESS_ORACLE_CODES = ("005930","000660","035420")` · `INDEX_FRESHNESS_MAX_CALENDAR_LAG = 5` · `INDEX_BAR_CONFIRM_HHMM = (15, 40)`. 주석에 **「롤백은 이 값 하나」**를 명시.
- `collectors/index_writer.py` — 파일 끝에 순수 함수 추가(현재 `:1-32`, DB 의존 없음):
  - `reference_trade_date(rows_max_by_code, now)` → `cutoff` 계산(설계 §4-1)
  - `evaluate_freshness(index_code, table, max_date, ref_date, today, src)` → `{"index","table","max","ref","stale","axis","lag_days","src"}`
  - 축 A/축 B 를 **각각** 판정해 리스트로 돌려준다(합치지 않는다).

**테스트 먼저** — 새 파일 `tests/collectors/test_index_freshness.py`
- [ ] `cutoff`: 07:40 → `today-1` / 15:35 → `today-1` / 15:49 → `today` / 15:40 정각 → `today`
- [ ] 축 A: `max < ref` → stale, `max == ref` → fresh, `max > ref`(15:35 에 T 를 쓴 경우) → fresh
- [ ] 축 B: `today - max = 5` → fresh, `= 6` → stale
- [ ] 🔴 **07:40 오탐 회귀**(설계 §4-1 실측 근거): 오라클에 「오늘 날짜 행」이 섞여 있어도 07:40 에는 stale 이 **아니다**
- [ ] 두 축이 동시에 참일 때 **결과가 2개**로 나온다(한 줄로 뭉치지 않는다)

**수용**: 새 테스트 전부 통과 · `tests/collectors/test_index_writer.py` 2개 무변경 통과.

---

## Task 2 — KIS 래퍼 + 정규화 (테스트 먼저)

**파일**
- `api/kis_market_api.py` — `get_index_data`(`:402-450`) **바로 아래**에 추가:
  ```python
  def get_index_daily_chart(index_code="0001", start_yyyymmdd=None, end_yyyymmdd=None) -> Optional[pd.DataFrame]
  ```
  `get_inquire_daily_itemchartprice`(`:132-165`)의 형태를 그대로 따른다: `url`/`tr_id` 상수 → `params` → `kis._url_fetch` → `res.isOK()` → `pd.DataFrame(getattr(body,'output2',[]))`. 실패는 `logger.error` + `None`.
  URL = **`/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice`** · tr_id `FHKUP03500100` · `FID_COND_MRKT_DIV_CODE="U"` · `FID_ORG_ADJ_PRC="0"` (Task 0 실측).
  🔑 `_url_fetch` 가 404 에 **None** 을 주므로 `res` 가 falsy → 래퍼도 `None` → 호출자가 그걸 폴백 사유로 쓴다. «빈 output2» 는 **빈 DataFrame**(≠ None)으로 돌려 판정에 맡긴다.
- `collectors/index_writer.py` — `fdr_df_to_index_rows`(`:12-24`) 옆에 `kis_df_to_index_rows(index_code, df)` 추가. **Task 0 에서 확정한 키만** 쓴다 (`stck_bsop_date`·`bstp_nmix_oprc`·`bstp_nmix_hgpr`·`bstp_nmix_lwpr`·`bstp_nmix_prpr`·`acml_vol`, 거래량 ×1000). 출력 dict 는 기존과 **바이트 단위로 동일한 스키마**(`index_code/date/open/high/low/close/volume`, `date` 는 `YYYY-MM-DD`).

**테스트 먼저** — `tests/collectors/test_index_writer.py` 에 추가 (새 파일 안 만듦)
- [ ] `kis_df_to_index_rows`: `YYYYMMDD` → `YYYY-MM-DD` 변환
- [ ] 문자열 숫자(`"6995.39"`)를 float 로 캐스팅
- [ ] 빈 df → `[]`
- [ ] **정렬 무관**: 응답이 최신순이어도 결과 행 집합이 같다
- [ ] `fdr_df_to_index_rows` 와 **키 집합이 동일**(두 소스가 같은 계약을 낸다)
- 새 파일 `tests/api/test_index_daily_chart.py`: `kis._url_fetch` 를 monkeypatch → `tr_id == "FHKUP03500100"` · `FID_COND_MRKT_DIV_CODE == "U"` · `FID_INPUT_ISCD` 가 `"0001"/"1001"` · 실패 시 `None`

**수용**: 네트워크 0회(모킹 확인) · 기존 `api/` 테스트 무변경 통과.

---

## Task 3 — `collect_index` 소스 선택 + 신선도 + reconcile 행

**파일**
- `collectors/index_writer.py` — `upsert_index_reconciliation(conn, trade_date, real_rows, new_rows, overlap, coverage, verdict)` 추가. SQL 은 `collectors/sector_writer.py:654-673` 형식을 따르되 `dataset='index'`, `value_match_rate` 는 **NULL 로 둔다**. `try/except → rollback → raise` 도 동일.
- `collectors/index_collector.py:27-37` — `collect_index` 를 다음으로 교체(함수 시그니처 `(start=None)` **유지**):
  1. `INDEX_DAILY_SOURCE == "kis"` 면 `auth()` 후 `get_index_daily_chart` → `kis_df_to_index_rows`; **예외면만** FDR 로 폴백하고 `src="fdr"` 로 기록.
  2. UPSERT **전에** `SELECT max(date) FROM index_daily WHERE index_code=%s` 로 직전 max 를 잡아 `new_rows` 를 센다.
  3. `SELECT max(date) FROM daily_prices WHERE stock_code IN %s AND date <= %s`(오라클·cutoff)로 `D_ref`.
  4. `evaluate_freshness` → stale 이면 `logger.warning("[index-freshness] …")`.
  5. `upsert_index_reconciliation(...)`.
  6. 반환: `{"KOSPI": n, "KOSDAQ": n, "src": src, "stale": [...]}` — 기존 두 키를 **그대로 두고 추가만** 한다.
- 🔴 함수명은 `check_index_freshness` — `reconcile_index`/`reconcile_verdict`/`_LEGACY_CODE_MAP` 는 `tests/collectors/test_index_collector.py:25-28` 가 막고 있다.
- `collectors/eod_collection.py` 는 **안 고친다**(`:51` 그대로). `bot/system_monitor.py` 도 **안 고친다**(`:653,662` 가 dict 를 f-string 으로 흘린다).

**테스트 먼저** — `tests/collectors/test_index_collector.py` 에 추가
- [ ] 기존 3개(`test_index_tickers_map` · `test_legacy_reconcile_helpers_are_gone` · `test_collect_index_is_still_exported`) **무변경 통과**
- [ ] `INDEX_DAILY_SOURCE="kis"` 일 때 **FDR 을 import 조차 하지 않는다**(모듈 스텁 주입 후 호출 0 확인)
- [ ] KIS 가 예외 → FDR 폴백 · 결과 `src == "fdr"`
- [ ] KIS 가 **빈 결과** → 폴백 **안 함** · 0행 · stale 발화 (설계 §3)
- [ ] stale 시 반환 dict 의 `stale` 에 지수 코드가 담긴다 / 정상이면 `[]`
- [ ] `new_rows` 가 「소스가 준 행 수」가 아니라 「직전 max 보다 뒤인 행 수」다 — **6행을 줬는데 새 날짜 0개면 `new_rows==0`**(이번 결함의 회귀 고정)
- [ ] reconcile upsert 가 `dataset='index'`·ISO 날짜·`value_match_rate=None` 으로 호출된다

**수용**: DB·네트워크 모킹 · `tests/collectors/test_eod_collection.py` 전부 무변경 통과.

---

## Task 4 — `refresh_regime_indices` 소스 선택 + 신선도

**파일**
- `core/regime/index_refresh.py:45-87` — `fdr=None` 주입 이음매(`:51,58-59`)를 **유지**하고 `kis=None` 이음매를 나란히 추가한다(테스트 주입용).
  1. `INDEX_DAILY_SOURCE == "kis"` 면 KIS 경로, 예외면 기존 FDR 재시도 루프(`:63-78`, `_MAX_FDR_RETRIES=3`)로 폴백.
  2. `price_repo.save_daily_prices_batch(name, daily)` 호출은 **그대로**(`:81`) — `past_rows_insert_only` 기본 False 유지(`db/repositories/price.py:74-77` 의 W3 의도).
  3. 쓴 뒤 신선도 판정 → `logger.warning("[index-freshness] … table=daily_prices …")`.
  4. 반환 dict 는 `{"KOSPI": n, "KOSDAQ": n}` **형태를 깨지 않는다** — `bot/system_monitor.py:619-622` 가 `min(res.values()) > 0` 로 판단한다. ⇒ stale 목록은 **로그로만** 내보내고 dict 에 넣지 않는다.
- 🔴 **import 방향**: `core/regime/index_refresh.py` 는 `collectors.index_writer` 를 **함수 안에서 지연 import** 한다(`collectors/eod_collection.py:22` 가 이미 `core.regime` 를 import 하므로 모듈 수준 상호 import 를 만들면 순환 위험). 기존 `import FinanceDataReader`(`:59`)와 같은 자리에 둔다.
- `D_ref` 조회는 `price_repo` 가 아니라 **새 SQL 을 추가하지 않고** `price_repo.get_daily_prices(code, days=…)` 로 오라클 종목 max(date) 를 얻는다(신규 DSN 금지). 반환 df 가 비면 「모른다」 → **stale 로 접지 않고** `unknown` 으로 1줄 남긴다(「모른다」를 「안전」으로도 「고장」으로도 접지 않는다).

**테스트 먼저** — `tests/test_regime_index_refresh.py` 에 추가 (기존 5개 무변경 통과 필수)
- [ ] `INDEX_DAILY_SOURCE="kis"` → KIS 스텁 호출, FDR 스텁 **미호출**
- [ ] KIS 예외 → FDR 3회 재시도 폴백이 **그대로 동작**
- [ ] 한 지수 실패가 다른 지수를 막지 않는다(기존 격리 계약 유지)
- [ ] 반환 dict 키가 정확히 `{"KOSPI","KOSDAQ"}` 다(추가 키 금지 회귀)
- [ ] stale 이면 `[index-freshness]` 가 `caplog` 에 잡힌다 / 정상이면 안 잡힌다
- [ ] `save_daily_prices_batch` 가 `past_rows_insert_only=True` 로 **불리지 않는다**
- [ ] `tests/test_w1_past_rows_insert_only.py:310` 무변경 통과

---

## Task 5 — 회귀 게이트 · 문서 · 커밋

- [ ] 워크트리에서 전체 스위트: `python -m pytest -q` (🔴 **09:10 KST 이후** · 라이브 트리 아님)
- [ ] 실패 **집합**을 기준선 `D:/tmp/main_baseline_failures_20260907.txt`(15줄)와 **양방향 차분** → 새로 생긴 것 0 · 사라진 것 0
- [ ] `git diff --stat` 로 **운영 파일 5개 이하** 확인. `bot/`·`db/`·`strategies/`·`framework/` 접촉 0
- [ ] 설계 문서 §2 의 「실측 필요」를 Task 0 결과로 채워 갱신
- [ ] 커밋 메시지는 **파일 또는 히어도큰**으로(인라인 금지). `--no-ff` 머지는 **09:00~15:30 밖**
- [ ] push 후 귀속 확인: `gh api repos/<o>/<r>/commits/<sha> --jq .author.login` 이 `null` 이 **아님**

---

## 최종 검증 체크리스트

### A. 머지 전 (워크트리)
- [ ] Task 0 프로브 결과가 문서에 반영됐다(추측 필드 0개)
- [ ] 새 테스트가 네트워크·DB 를 **한 번도** 타지 않는다(`.env` 없는 워크트리에서 통과가 증거)
- [ ] 회귀 실패 집합 양방향 차분 0
- [ ] 운영 파일 5개 이하 · 리팩터 0 · `TODO`/`skip`/`only` 0건
- [ ] 롤백 상수 1개(`INDEX_DAILY_SOURCE`)로 되돌아가는지 테스트로 고정했다

### B. 첫 라이브 EOD «다음날 아침» 1회 (읽기 전용 · psql SELECT)
```sql
SELECT index_code, max(date), count(*) FROM index_daily GROUP BY 1;
SELECT stock_code, max(date), count(*) FROM daily_prices
 WHERE stock_code IN ('KOSPI','KOSDAQ') GROUP BY 1;
SELECT stock_code, date, close FROM daily_prices
 WHERE stock_code IN ('KOSPI','KOSDAQ') AND date IN ('2026-09-08','2026-09-09') ORDER BY 1,2;
SELECT * FROM collection_reconciliation WHERE dataset='index' ORDER BY trade_date DESC LIMIT 3;
SELECT stock_code, max(date) FROM daily_prices
 WHERE stock_code IN ('KS11','KQ11') GROUP BY 1;   -- 2026-07-08 에서 «변하지 않아야» 한다
```
- [ ] P1·P2: 두 표 max(date) = 그날 거래일
- [ ] P3: 09-08 KOSPI ≈ 6,955 / KOSDAQ ≈ 812 · 09-09 KOSPI ≈ 7,052 / KOSDAQ ≈ 830 (±1)
- [ ] P4: 두 표의 증가분이 같다
- [ ] P5: 09-01~09-07 종가 불변
- [ ] P7: reconcile `verdict='PASS'` · `new_rows` = 신규 거래일 수 · `value_match_rate` NULL
- [ ] `KS11`/`KQ11` max(date) 가 **2026-07-08 그대로**(건드리지 않았다는 음성 대조)

### C. 로그 (같은 날 아침, 읽기 전용 grep)
- [ ] P8: 07:40 구간에 `[index-freshness]` **0건**(오탐 없음)
- [ ] P6: `[벤치마크]` 한 줄의 지수 레벨·당일 % 형식·값이 종전과 동일
- [ ] EOD 요약 `지수 {...}` 에 `'src': 'kis'` 와 `'stale': []` 가 보인다
- [ ] F2 관측: 15:35 에 기록된 T 종가 vs 16:18 벤치마크 값 대조 결과를 EOD 리포트에 **숫자로** 적는다(가드는 안 단다)
- [ ] 🔴 **F2′ 관측 — 첫 라이브일 07:40 «직후»(≤ 08:30) 1회, 읽기 전용**. KIS 는 장 시작 «전»에도 T 라벨 봉을 준다(2026-09-10 리뷰 실측). 아래를 그날 «안에» 찍어 둔다 — **07:40 원본은 EOD UPSERT 로 덮여 사후 복원이 불가능하다**(`updated_at = created_at` 인 행 0건).
  ```sql
  SELECT index_code, max(date), count(*) FROM index_daily GROUP BY 1;
  SELECT stock_code, date, open, high, low, close, volume, created_at
    FROM daily_prices WHERE stock_code IN ('KOSPI','KOSDAQ')
     AND date = to_char(now() AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD') ORDER BY 1;
  ```
  판정: ①T 행이 **없으면** 설계 §6 전제(07:40 은 T−1 까지)가 맞다 ②T 행이 **있으면** 그 값이 가마감인지(종가 ≠ 0 · 전일과 다름) 기록하고, `[index-freshness]` 가 그날 07:40 에 **무음**이었는지 함께 적는다(무음이면 축 A·B 가 당일 봉으로 무력화된 것) ③`close = 0` 행은 코드가 이미 버리므로 **0건이어야 한다**
- [ ] ERROR **집합** 차분 0 (총건수와 차분은 따로 적는다)

### D. 라이브 무해 증명
- [ ] `virtual_trading_records`·`paper_strategy_equity`·포지션 복원 3표 불변
- [ ] 매수·매도 건수·전략별 손익이 소스 전환일 전후로 설명 가능한 범위


---

## 실행 기록 (2026-09-10 · 브랜치 `feat/index-kis-freshness`)

- Task 0 ✅ 프로브 완료 → `scratchpad/index_kis_probe/RESULT.md` (설계 §2·§2-1 갱신 반영).
- Task 1~4 ✅ 구현·테스트 완료. 운영 파일 **정확히 5개**(`config/constants.py` · `api/kis_market_api.py` · `collectors/index_writer.py` · `collectors/index_collector.py` · `core/regime/index_refresh.py`). `bot/`·`db/`·`strategies/`·`framework/`·`collectors/eod_collection.py` 접촉 **0**.
- 설계와 달라진 7건은 설계 문서 **§13 구현 노트**에 표로 남겼다(URL 정정 · None=장애 · 판정 함수 위치 · `kis=` 이음매 · known/unknown 2튜플 · cutoff 자르기 위치 · 폴백 단위).
- 🔑 테스트 캡처 장치 주의: `utils.logger.setup_logger` 는 `propagate=False` 라 **pytest 기본 로그 픽스처가 이 로거를 못 본다**. 신선도 로그 검증은 모듈 logger 에 핸들러를 직접 붙여야 한다(그렇게 안 하면 「경보가 안 났다」와 「캡처가 못 봤다」가 구분되지 않는다).
- Task 5 ⬜ **전체 회귀 게이트는 09:10 KST 이후** — 기준선 `D:/tmp/main_baseline_failures_20260907.txt`(15줄)와 실패 **집합 양방향 차분**. 머지는 09:00~15:30 «밖».
- Task 5 ⬜ 첫 라이브 EOD **다음날 아침** 읽기 전용 SELECT(최종 검증 체크리스트 B) — 특히 **KOSDAQ 행이 실제로 들어왔는지**(프로브에서 `1001` 은 이 경로로 미검증)와 `KS11`/`KQ11` max(date) 가 2026-07-08 그대로인지.
