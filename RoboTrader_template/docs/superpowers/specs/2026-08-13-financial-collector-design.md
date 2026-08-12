# 재무 수집기 (DART as-filed + KIS 분기비율) — 설계 (2026-08-13)

> **성격**: 데이터 수집 인프라. **소비자는 아직 확정하지 않았다** — 사장님 선택은 「일단 모아두기」다.
> **라이브 매매 동작 0줄.** 변경은 EOD 수집 경로 `eod_collection.py` **2줄**(collect 1 · reconcile 1).
> 발효는 다음 07:40 재기동부터.

---

## 0. 왜 지금, 왜 이것인가

발단은 2026-08-12 사장님 질문 *「8전략·태쏘 전략의 정확도를 높이려 퀀트 데이터를 쓰고 싶다.
DART에서 오나? 분기마다 있나?」* 였다. 인벤토리 조사 결과 → [[changelog-2026-08-12-quant-data-inventory-and-universe-fix]]

### 사실 ①: 분기 데이터는 「없는」 게 아니라 「안 받은」 것이다

DART·KIS **둘 다 분기를 지원한다.** 우리가 연간만 받고 있었을 뿐이다.

- `dart_client.py` 계열: `REPRT_FY="11011"`(사업보고서) 고정으로 수집됐다.
- `api/kis_financial_api.py:84` `div_cls: str = "0"` — 🔧 **이건 하드코딩이 아니라 「기본값 파라미터」다.**
  호출자가 `"1"` 을 넘기면 분기가 온다. 실제 호출자 4곳(`lynch/strategy.py:348`·`lynch/screener.py:113`·
  `sawkami/strategy.py:306`·`sawkami/screener.py:157`)이 **전부 기본값을 써서** 결과가 연간 고정이었다.
  ⇒ **KIS 쪽은 API 코드 수정이 필요 없다.**

### 사실 ②: 기존 `dart_financials_asfiled` 는 고칠 수 없다 — 키가 틀렸다

실측 스키마(2026-08-13, `kis_template`):

```
PRIMARY KEY (stock_code, bsns_year)
컬럼 13개 — reprt_code 없음 · rcept_no 없음
```

🔴 문제는 「정정공시가 덮어쓴다」보다 **한 겹 깊다**:

1. **`reprt_code` 컬럼이 없다** ⇒ 분기를 담을 **차원 자체가 없다.** 1Q·반기·3Q·사업보고서가 전부
   같은 `bsns_year` 한 칸으로 들어온다.
2. **`rcept_no` 컬럼이 없다** ⇒ 어느 접수건에서 온 값인지 **식별할 수단이 없다.**
   `rcept_dt`(날짜)만으로는 같은 날 접수된 원본/정정을 못 가른다.

⇒ 정정공시를 「덮어쓰지 않게」 만들려 해도 **현 스키마로는 원본과 정정을 구분조차 못 한다.**
🔑 ***이 테이블이 죽은 이유는 컬럼이 모자라서가 아니라 키가 「기간」이었기 때문이다.***

**실측 규모**: 3월 외 접수 **16.1%** · 결산일 대비 지연 p05=70 · p50=80 · p95=228 · **p99=735** ·
max=2,311일. 2019 사업연도 건이 **2026-04-29** 에 접수된 예가 실재한다.

### 사실 ③: 기존 테이블을 새로 만들어도 아무것도 안 깨진다

`dart_financials_asfiled` 를 참조하는 코드를 전수 조사했다(2026-08-13).

| 위치 | 참조 |
|---|---|
| **`main` 체크아웃** | **코드 0줄** — 문서 언급뿐(`specs/2026-08-08-*` · `plans/2026-08-08-*`) |
| 브랜치 `feat/fundamental-risk-filter-pit` | 3파일 — `p2_features.py` · `f4_load.py` · `tests/.../test_load_sql.py` |

⇒ **새 테이블을 만들어도 미병합 브랜치는 안 깨진다.** 기존 테이블은 **그대로 두고**,
Phase 2B 가 끝난 뒤 정리한다.

---

## 1. 결정 사항 (사장님 확정, 2026-08-13)

| 항목 | 결정 | 비고 |
|---|---|---|
| 배치 | **`collectors/` + EOD 등록** | 자동 수집·reconcile·경보가 따라온다 |
| 첫 범위 | **2026년치만** (1Q + 반기) | **5,112~10,224호출**(§6.1) · 소규모로 스키마 검증 먼저 |
| 소스 | **DART + KIS 둘 다** | 교차검증 가능. 🔴 KIS 는 PIT 불가 — §5 봉쇄 |
| 원장 키 | **A안 — 접수건 단위 append-only** | 정정 보존이 정책이 아니라 **구조** |
| 저장 형태 | **C안 — Long 원장 + Wide 파생** | (2026-08-12 합의 승계) |
| 원본 보관 | **JSONL.gz 파일 병행** | `f2_raw` 전례가 근거 |
| ~~KIS `observed_at`~~ | **채택 안 함** | 대신 §5 조회 계층 격리 |

### 원본 파일 보관의 근거 — `f2_raw` 가 이미 증명했다

`scratchpad/fund_pit/f2_raw.jsonl.gz`(101MB) 실측: **계정행 2,823,446 / 고유 `account_id` 2,461종.**
그런데 DB(`dart_financials_asfiled`)에는 **7개 지표 컬럼만** 뽑혀 있다.

🔑 ***원본을 남겨뒀기 때문에 「DART 호출 0건으로 재무를 확장할 수 있다」는 결론이 가능했다.***
파일이 없었으면 ~18,000호출을 다시 돌려야 했다. **파싱은 틀릴 수 있고, 원본은 그 유일한 보험이다.**

⚠️ 2026-08-13 `D:\archive\fund-pit-raw-20260813\` 로 사본 이관 완료(7/7 SHA256 일치).
`scratchpad/` 는 gitignore 대상이라 `git clean -xdf` 한 번에 사라지는 위치였다.

---

## 2. 구성요소

집 규약을 따른다 — `collector`(오케스트레이션) / `fetcher`(외부호출) / `writer`(DB).
`foreign_flow_collector` + `foreign_flow_fetcher` + `foreign_flow_writer` 3분할이 전례다.

| 파일 | 하는 일 | 의존 |
|---|---|---|
| `collectors/financial_collector.py` | 창 판정 · 대상 산출 · `collect_financials()` · `reconcile_financials()` | fetcher · writer |
| `collectors/dart_financial_fetcher.py` | `fnlttSinglAcntAll` 호출 · status 처리 · 원본 append | `requests` |
| `collectors/kis_financial_fetcher.py` | `get_financial_ratio(div_cls="1")` 래핑 | `api/kis_financial_api` |
| `collectors/financial_writer.py` | UPSERT 전담 — **DB 쓰기는 이 파일 한 곳뿐** | `db/kis_db_connection` |

**경계**: 각 파일은 하나의 질문에만 답한다. fetcher 는 「DART/KIS 가 무엇을 돌려주는가」,
writer 는 「그것을 어떻게 저장하는가」, collector 는 「지금 무엇을 받아야 하는가」.
fetcher 는 DB 를 모르고, writer 는 HTTP 를 모른다.

---

## 3. 스키마 (신규 3테이블 + 뷰 1개)

### 3.1 `dart_financial_filings` — 접수건 메타 (1행 = 1보고서)

```sql
CREATE TABLE dart_financial_filings (
    rcept_no      varchar(14) NOT NULL,   -- DART 접수번호
    fs_div        varchar(3)  NOT NULL,   -- CFS(연결) / OFS(별도)
    corp_code     varchar(8)  NOT NULL,
    stock_code    varchar(20) NOT NULL,
    bsns_year     varchar(4)  NOT NULL,
    reprt_code    varchar(5)  NOT NULL,   -- 11011 사업 / 11012 반기 / 11013 1Q / 11014 3Q
    rcept_dt      date        NOT NULL,   -- 🔑 PIT 앵커
    is_amendment  boolean     NOT NULL DEFAULT false,
    raw_path      text,                   -- 'dart_20260813.jsonl.gz#L1234' — 원본 역추적
    collected_at  timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (rcept_no, fs_div)
);
CREATE INDEX idx_dff_key   ON dart_financial_filings (stock_code, bsns_year, reprt_code, rcept_dt);
CREATE INDEX idx_dff_rcept ON dart_financial_filings (rcept_dt);
```

`fs_div` 가 키에 있는 이유: `fnlttSinglAcntAll` 은 `fs_div` 를 **요청 파라미터로 받는다.**
한 접수건에 연결/별도 두 재무제표가 있으므로 둘 다 받으면 같은 `rcept_no` 로 2행이 된다.

`is_amendment`: 같은 `(stock_code, bsns_year, reprt_code)` 에 **더 이른 `rcept_dt` 접수건이 이미 있으면** true.
⚠️ **파생값이지 DART 가 주는 값이 아니다** — 수집 순서에 따라 나중에 뒤집힐 수 있다
(옛 접수건을 뒤늦게 받으면). **판정 기준으로 쓰지 말고 `rcept_dt` 로 직접 정렬할 것.**

### 3.2 `dart_financial_accounts` — Long 원장 (1행 = 1계정)

```sql
CREATE TABLE dart_financial_accounts (
    rcept_no          varchar(14) NOT NULL,
    fs_div            varchar(3)  NOT NULL,
    sj_div            varchar(8)  NOT NULL,   -- BS/IS/CIS/CF/SCE
    account_id        text        NOT NULL,   -- 'ifrs-full_Assets' 등
    ord               int         NOT NULL,   -- 응답 내 순서
    account_nm        text,
    thstrm_amount     bigint,                 -- 당기
    frmtrm_amount     bigint,                 -- 전기
    bfefrmtrm_amount  bigint,                 -- 전전기
    currency          text,
    PRIMARY KEY (rcept_no, fs_div, sj_div, account_id, ord),
    FOREIGN KEY (rcept_no, fs_div) REFERENCES dart_financial_filings (rcept_no, fs_div)
);
```

🔑 **`ord` 를 키에 넣는 이유**: DART 응답에서 같은 `account_id` 가 한 보고서에 **두 번 이상** 나올 수 있다
(표준계정코드 미사용분 16.3%, `account_id='-표준계정코드 미사용-'`). `ord` 없이 키를 잡으면
***두 번째 행이 조용히 사라진다*** — 지금 테이블이 당한 것과 같은 형태다.

**규모 추정**: 계정행 실측 평균 = 2,823,446 / 17,892레코드 ≈ **158행/보고서.**
2026년치(2,556종목 × 2보고서) ≈ **80만 행.** 2015~ 전체 소급 시 ≈ 1,600만 행 / 6~8GB.

### 3.3 `kis_financial_ratio` — KIS 분기 비율

```sql
CREATE TABLE kis_financial_ratio (
    stock_code   varchar(20) NOT NULL,
    stac_yymm    varchar(6)  NOT NULL,   -- 결산년월
    div_cls      varchar(1)  NOT NULL,   -- '0'=연간 '1'=분기
    roe_value                numeric,
    per                      numeric,
    eps                      numeric,
    sps                      numeric,
    bps                      numeric,
    reserve_ratio            numeric,
    liability_ratio          numeric,
    sales_growth             numeric,
    operating_income_growth  numeric,
    net_income_growth        numeric,
    raw_json     jsonb,
    PRIMARY KEY (stock_code, stac_yymm, div_cls)
);
```

🔴 **접수일 컬럼이 없다 — 의도적이다.** KIS 응답에 접수일이 없으므로 PIT 앵커를 만들 수 없다.
***PIT 앵커가 없는 데이터에 날짜 컬럼을 붙이면 누군가 그걸 PIT 으로 쓴다.***
`collected_at` 조차 두지 않는다(그것도 앵커로 오용될 수 있다). 봉쇄는 §5 참조.

### 3.4 `fn_financials_as_of(p_as_of date)` — Wide 파생

`rcept_dt <= p_as_of` 인 접수건 중 `(stock_code, bsns_year, reprt_code)` 별로
`ORDER BY rcept_dt DESC, rcept_no DESC LIMIT 1` 을 골라 **13지표**를 넓게 편다.

| # | 지표 | # | 지표 |
|---|---|---|---|
| 1 | 자산총계 | 8 | 이자비용 |
| 2 | 자본총계 | 9 | 금융원가 |
| 3 | 자본금 | 10 | 이자지급(CF) |
| 4 | 부채총계 | 11 | 영업활동현금흐름 |
| 5 | 매출액 | 12 | 투자활동현금흐름 |
| 6 | 영업이익 | 13 | 재무활동현금흐름 |
| 7 | 당기순이익 | | |

**뷰/함수로 시작한다.** 2026년치 80만 행 규모에서 성능 문제가 없고, 지금 머티리얼라이즈드 테이블을
만들면 **갱신 누락 위험만 먼저 생긴다.** 소급 확대로 커지면 그때 전환한다(전환 시 뷰와 테이블의
값 일치를 대조 게이트로 걸 것).

⚠️ **`account_id` → 13지표 매핑표는 구현 시 실측으로 만든다.** ifrs 표준 50.1% · `dart_` 확장 33.6% ·
표준계정코드 미사용 16.3% 라 **한 지표에 여러 `account_id` 가 대응한다.** 매핑 커버리지를
`f3_coverage.txt` 형식으로 리포트하고, **커버리지가 아니라 「매핑 실패 종목 목록」을 산출물로 남긴다**
(비율만 남기면 어느 종목이 빠졌는지 못 찾는다).

---

## 4. 데이터 흐름

```
eod_collection.run_data_collection(trade_date)
  ├─ daily / minute / index / stock_market / foreign_flow
  ├─ corp_events              ← opendart (기존)
  └─ _safe(collect_financials, trade_date)     ← 신규. corp_events «다음» 에 둔다
       ├─ ① 창 판정 → 창 밖이면 즉시 no-op (DART 호출 0)
       ├─ ② 대상 = load_universe() ∩ corp_code 매핑(2,556) − 이미 수집분 − 013 확정분
       ├─ ③ DART fnlttSinglAcntAll  (CFS 시도 → status 013 이면 OFS 재시도)
       │      ├─ 응답 원본 → scratchpad/financials/dart_YYYYMMDD.jsonl.gz (append)
       │      └─ 파싱 → filings 1행 + accounts N행
       ├─ ④ KIS get_financial_ratio(div_cls="1") → kis_financial_ratio UPSERT
       └─ ⑤ 요약 dict 반환
```

🔴 **순차여야 한다.** `corp_events_collector` 가 **같은 opendart 호스트**를 쓴다.
2026-08-06 실측: 4스레드 동시요청으로 opendart 전 호스트가 리셋됐고 루트 페이지조차 `curl` 로 reset 됐다.
`eod_collection` 은 이미 순차 실행이므로 순서만 지키면 된다.

---

## 5. 🔴 KIS look-ahead 봉쇄 — 구조로 막는다

사장님이 「DART + KIS 둘 다」를 선택했다. KIS 는 **접수일이 없어 PIT 을 못 준다.**
이 프로젝트는 「죽은 가드」에 여섯 번 당했으므로 **주석·문서 경고로는 막지 않는다.**

| 겹 | 조치 |
|---|---|
| 1 | `kis_financial_ratio` 에 **날짜형 컬럼을 두지 않는다**(위 3.3) |
| 2 | **PIT 조회 경로(`fn_financials_as_of` · `pit_reader`)가 이 테이블을 참조하지 않는다** |
| 3 | **테스트가 2번을 고정한다** — PIT 소스 목록에 `kis_financial_ratio` 가 없음을 단언 |

용도는 **교차검증 전용**이다: 같은 분기에 대해 「DART 원시계정으로 계산한 비율」과
「KIS 가 준 비율」이 맞는지 대조한다. ⚠️ 불일치가 나와도 **어느 쪽이 옳은지는 이 설계가 판정하지 않는다.**

---

## 6. 스케줄

### 6.1 수집 창

| 보고서 | 법정기한 | 창 | 창 길이 |
|---|---|---|---|
| 사업 (11011) | 3/31 | **04/03 ~ 05/10** | 38일 |
| 1Q (11013) | 5/15 | **05/18 ~ 06/20** | 34일 |
| 반기 (11012) | 8/14 | **08/17 ~ 09/20** | 35일 |
| 3Q (11014) | 11/14 | **11/17 ~ 12/20** | 34일 |

(2026-08-12 합의된 창을 그대로 쓴다. 기한 **+3일** 여유를 둔 값이다 —
⚠️ 초안에 적었던 `08/15` 는 **토요일이라 EOD 가 안 돈다**. 창 시작은 반드시 영업일이어야 한다.)

창 밖이면 **즉시 no-op**(DART 호출 0). 창 안이면 미수집분만, **일일 상한 800**(⚠️ **DART 호출 기준**.
KIS 호출은 별도 계산 — KIS 는 DART 일일 한도와 무관하다).

**호출량 산정 근거** — `fnlttSinglAcntAll` 은 `(corp, year, reprt, fs_div)` 1건당 1호출이다.

| | 호출 |
|---|--:|
| 보고서 1종 × 2,556종목 (CFS 성공 가정) | **≈ 2,556** |
| + OFS 폴백분 (연결재무제표 없는 회사, 비율 미실측) | 최대 +2,556 |
| **보고서 1종 실효 범위** | **2,556 ~ 5,112** |
| 2026년치 = 1Q + 반기 (2종) | **5,112 ~ 10,224** |
| 전체 소급 2015~ = 4종 × 11년 | **≈ 112,000** |

⚠️ **OFS 폴백 비율은 실측하지 않았다.** 상한으로 계획하고, 백필 1회차에서 실측해 이 표를 갱신할 것.
창 35일 × 800 = **28,000** 이라 반기 1종(최대 5,112)에는 넉넉하다.

### 6.2 🔴 백필 모드 — 창만으로는 2026 1Q 를 영영 못 받는다

**오늘은 2026-08-13 이고 1Q 창(05/18~06/20)은 이미 지났다.** 창 기반 증분만 만들면
*첫 목표인 2026 1Q 를 한 건도 안 받는다.* 그래서 백필 경로가 설계에 **반드시** 들어간다.

```
python -m collectors.financial_collector --backfill --year 2026 --reprt 11013 --interval 0.34
```

- 창을 무시하고 **미수집분만** 채운다. **수동 실행, EOD 밖.**
- `--interval 0.34`(3 req/s)는 **실측 안전값**이다 — B1 시총 수집 20,241호출 동안 **연결 리셋 0**.
  1Q 1종 = 2,556~5,112호출 ≈ **15~29분**.
- ⚠️ **평일 16:00 EOD 와 겹치면 안 된다**(corp_events 가 같은 호스트).
- 🔑 이 하네스가 그대로 **2015~ 소급 확대의 하네스**가 된다 — `--year` 만 늘리면 된다
  (전체 ≈112,000호출 · 6~7일 · 6~8GB).

**구체적 순서**: ①오늘 백필로 2026 1Q 를 채운다 → ②**8/17(월)** 에 창이 열리면 반기가 **자동으로** 들어온다.
(2026 반기 법정기한이 **8/14 = 내일**이다. 2025 반기 접수일이 정확히 **8/14 = 기한 당일**이었으므로
접수는 기한에 몰릴 것으로 본다 — 창 첫날 잔량이 크게 잡히는 게 정상이다.)

### 6.3 정정 스윕 (주 1회)

⚠️ **창만으로는 정정공시·지연공시를 놓친다** — 3월 외 접수 16.1%, p99 735일.

보완: 창과 무관하게 **주 1회**, 최근 N일 `list.json` 으로 정정보고서(`[기재정정]` 접두)를 찾아
**해당 접수건만** 재수집한다. `corp_events_collector` 가 이미 쓰는 경로라 추가 비용이 작다.

---

## 7. 에러 처리

| 상황 | 처리 | 근거 |
|---|---|---|
| `OPENDART_API_KEY` 부재 | WARNING + 스킵. **EOD 비차단** | `corp_events_collector:229` 전례 |
| `status=020` 한도초과 | **즉시 중단 + 체크포인트 보존.** 조용히 0건으로 안 채운다 | B1 이 22:35 에 감지·중단, 00:10 재개로 무손실 |
| `status=013` 무자료 | 정상 종료. 🔑 **「무자료 확정」과 「미수집」을 구분 기록** | 안 하면 매일 같은 것을 두드린다 |
| `status=800` 점검 | 지수 백오프 재시도 | `dart_mcap_common:184` |
| 연결 리셋 3연속 | `DartBlocked` 예외. **동시 요청 금지** | 2026-08-06 IP 차단 |
| 파싱 실패 | **`None`. 절대 `0` 아님** | `parse_num` 규약. 원본이 파일에 있으니 재파싱 가능 |
| 페이지/목록 절단 | **WARNING 필수** | 무징후 절단 금지 — `corp_events_collector:155` |
| 단계 실패 | `_safe()` 격리 → EOD 비차단 | `eod_collection:24` |

---

## 8. reconcile

`reconcile_financials(trade_date)` → `collection_reconciliation(dataset='financials')`

- **창 밖** → `PASS`, `reason='out_of_window'`. **no-op 을 실패로 세지 않는다.**
- **창 안** → 두 조건을 **모두** 본다:
  1. **도달성** — `status ∈ {000, 013}`
  2. **진척률** — 미수집 잔량이 **3일 연속 안 줄면 `FAIL`**

🔑 ***2번이 「조용히 안 돌아감」을 잡는 유일한 장치다.*** 이번 **일봉 결손 49,252행 / 257종목**이
정확히 그 형태였다 — `load_universe` 가 `daily_prices` 자기 자신을 읽는 자기충족적 순환이라
한 번 빠진 종목은 **스스로 복구되지 않았고**, 2024-03-01~2026-06-14 **2년 5개월 동안 아무 경보도 안 울렸다.**
도달성만 보면 이 수집기도 같은 함정에 빠진다(**호출은 성공하는데 잔량이 안 줄어드는** 상태).

---

## 9. 테스트 (전부 red 먼저)

| # | 무엇 | red 조건 |
|---|---|---|
| 1 | **정정 보존** — 같은 `(stock,year,reprt)` 에 `rcept_no` 다른 2건 → **2행 다 남는가** | 현 스키마면 1행 |
| 2 | **as_of 대칭 단언** — 정정 접수일 *전*/*후* 로 두 번 물어 **다른 값**이 나오는가 | 🔑 단독 단언은 판별력 0 |
| 3 | **look-ahead 방어** — `rcept_dt > as_of` 접수건이 뷰에 **안 나오는가** | |
| 4 | **창 밖 no-op** — DART 호출 횟수 **0** 단언(mock call count) | |
| 5 | **013 재시도 제외** — 무자료 확정분을 다음 실행에서 다시 안 두드리는가 | |
| 6 | **020 중단** — 즉시 중단 + 기적재분 무손상 + 체크포인트 보존 | |
| 7 | **PIT 소스 격리** — PIT 조회 경로가 `kis_financial_ratio` 를 **참조하지 않는가** | §5 3번째 겹 |
| 8 | **파싱 실패 = None** — `0` 으로 안 뭉개는가 | |
| 9 | **라이브 불변** — `daily_prices`·`minute_candles`·`virtual_trading_records` 무변경 증명 | |
| 10 | **진입점 실호출** — `run_data_collection()` 을 **실제로 돌려** 호출열에 `collect_financials` 가 있는가 | 🔑 아래 |

🔑 **10번이 필요한 이유**: ***소스 문자열 단언은 죽은 경로에서도 통과한 전례가 있다.***
`ctx.sell` 의 `**kwargs` 가 `signal=` 을 조용히 삼켜 전달 실패가 안 드러난 사고(`9b82eec`),
그리고 복원 포지션 주입이 `on_init` 뒤에 오도록 **테스트는 올바른 순서로 쓰여 있었는데**
프로덕션만 반대였던 사고(`8238f91`)가 있었다. **배선은 실제로 돌려서 단언한다.**

**회귀 판정**: 전체 스위트를 **stash 후 베이스라인과 실패 «집합» 차분**으로 대조한다
(`c6dc77c` 방식). 자기보고로 「회귀 0」이라 적지 않는다.
⚠️ 전체 스위트는 **repo 루트 + VS 번들 Python** 에서만 완주한다 → [[reference-pytest-full-suite-invocation]]

---

## 10. 라이브 영향과 경계

| | |
|---|---|
| 매매 동작 변경 | **0줄** |
| `eod_collection.py` | **+2줄** (`_safe(collect_financials, ...)` · reconcile 1줄) |
| 기존 테이블 | **무변경** — `dart_financials_asfiled` 포함. 신규 3테이블 + 뷰 1개만 생성 |
| 발효 | 다음 **07:40 재기동** 후 첫 16:00 EOD |
| 롤백 | `eod_collection.py` 2줄 제거로 즉시. 테이블은 남겨도 무해(읽는 코드가 없다) |

**범위 밖 (이 설계가 하지 않는 것)**

- 🔴 **`multiverse/data/pit_reader.py:9` 의 「공시 lag 60일」 수정** — 실측 p05(70일)보다도 짧아
  백테스트가 재무를 약 20일 일찍 본다(방향이 look-ahead). **별건 백로그**로 남긴다.
- 🔴 **`dart_financials_asfiled` 폐기** — Phase 2B 가 끝난 뒤 별도 판단.
- 🔴 **2015~ 소급 백필 실행** — 하네스는 만들지만 **실행은 별도 승인**(112,000호출 · 6~7일).
- 🔴 **소비자 구현** — 「일단 모아두기」가 결정이다. 무엇에 쓸지는 데이터를 본 뒤 정한다.

⚠️ **이 마지막 항목의 위험을 명시해둔다**: ***소비자가 없으면 데이터가 맞는지 판정할 수 없다.***
따라서 §9 의 테스트는 「소비자 없이도 검증 가능한 성질」(정정 보존·look-ahead·no-op·중단 안전)에
집중돼 있고, **값의 정확성은 KIS 교차검증(§5)이 유일한 외부 대조**다.

---

## 11. 완료 판정

1. 2026 1Q 백필 완료 — 대상 종목 대비 `filings` 적재율 리포트 + **미적재 종목 목록**
   (⚠️ 비율만 남기지 말 것)
2. 테스트 10개 통과 + 전체 스위트 실패 집합 차분 **동일**
3. **8/17(월)** 창 개시 후 첫 EOD 에서 `collection_reconciliation(dataset='financials')` **PASS**
   (⚠️ 8/15 는 **토요일·광복절**이라 EOD 가 돌지 않는다)
4. `raw_path` 로 임의 3건을 골라 **DB 값 ↔ JSONL.gz 원본** 대조 일치
5. `daily_prices` 등 라이브 테이블 무변경 증명

[[changelog-2026-08-12-quant-data-inventory-and-universe-fix]] · [[reference-pytest-full-suite-invocation]] ·
[[changelog-2026-08-08-fundamental-risk-filter]]
