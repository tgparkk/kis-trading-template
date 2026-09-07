# 섹터 기반 데이터 (종목→업종 명부 + 업종 일별 성적표) — 설계 v5.1 (2026-09-06)

> 사장님 결정(2026-09-06 저녁): 「섹터 데이터 구축 — 공통 기반 둘 다 · A 먼저, 접근법 1(일봉 계산형)」 · 밤: 「분류체계 = KSIC 셋으로 통일」.
> 1차 소비자 = NewsQuant 섹터 고도화(스펙 B, 별건) · 문서 3(ma20 「같은 업종이 함께 눌렸나」 `Ps` 축) · 10월 말 라이브 매수 후보 표시.
> 이 문서는 **A 만** 다룬다. 뉴스 집계·API·라이브 표시는 범위 밖이다.

> **이력** — v1(초안) → critic 1차 REQUEST_CHANGES(블로커 9·주요 6: T6 손계산·오라클 차집합·5% 가드·값 없음·FDR 실체·유니버스 두 이름·EOD 픽스처·LOO·20일 창·시장별 하한·같은 날 PK·EOD 자리·ksic5) → **v2**(KRX 79업종 제외 · KSIC 셋 · 이름표 데이터 생성) → critic 2차 REQUEST_CHANGES(블로커 2·주요 7: 오라클에 DART 채움 클래스 누락 · 부트스트랩 명령 부재·98% 도달 순서 · 0220WL 전제 오류 · §8 분자/분모 · 얼어붙은 명부 미감지 · 소스 기준일 미기록 · 이름표 NULL 키 · SCD2 역전 CHECK · 소형 시장 하한) → **v3** → critic 3차 REQUEST_CHANGES(2차 항목 전부 해소 확인 · 신규 주요 6: §8 게이트의 전일 상태 저장소 부재 · §8-4 영구 WARN · `--bootstrap` 시간 가드 · 캐시 파일명 = 게시일 · T9 import 경로 · 2024-03 이전 비교 불가 · 경미 11) → **v4** → critic 4차 REQUEST_CHANGES(3차 항목 20건 전부 해소 확인 · 신규 주요 4: KSIC 코드 재확인 경로 부재 · `no_prev` 문턱 과대(기저 0~3 vs 2026-08-05 189) · `value_match_rate` 의미 역전 · 실패 경로 미정의 · 경미 9) → **v5** → critic 5차 **APPROVE**(4차 항목 17건 전부 해소 확인 · 코딩 전 반영 5 + 다듬기 8 → 전부 반영) → **v5.1**(이 문서). 심사가 **재현 확인**한 것: §0 사실 전부 · §3.5 실사례 · T6 · EOD 자리 · 부트스트랩 후 커버리지 99.75% 도달 · 프로젝트 규칙 준수(KIS 0 · 라이브 3표 · adj_factor · KisDbConnection).

---

## 0. 왜 지금, 왜 이것인가

두 유니버스 이름을 먼저 정한다(문서 전체에서 이 둘만 쓴다):
- **U_market** = `stock_market` ∩ `config.constants.SQL_STOCK_ONLY`(`^[0-9][0-9A-Z]{5}$` · ⚠️ `lib/universe_filter` 의 같은 이름 상수와 다르다) = **2,772** (KOSPI 945 · KOSDAQ 1,827).
- **U_all** = `collectors.daily_collector.load_universe` = `stock_market ∪ daily_prices`(같은 술어) = **2,795**. 차집합 23 = 상장목록엔 없고 일봉만 있는 종목(상폐 등 · 전부 `stock_industry` 행 있음).

### 사실 ①: 섹터 데이터가 넷 있는데 넷 다 쓸 수 없다 (2026-09-06 실측)

| 표 | 내용 | 커버리지(U_market) | 이력 | 못 쓰는 이유 |
|---|---|---:|---|---|
| `stock_industry` | DART KSIC `induty_code` 2,556 (코드만) | 2,533 (91.4%) | 스냅샷 2026-08-07 09:38 · **운영 쓰기 코드 없음**(scripts 만) | 우선주·유니버스 확장분 239 결측 · 날짜 없음 |
| `stock_sector` | KRX 79업종(이름) 4,085 | 2,673 (96.4%) | 스냅샷(날짜 없음) | 이후 편입 98종목 없음 · `market` 열 100% KOSPI(오염) · 「기타」 1,261 은 전부 유니버스 밖 · **갱신 소스 없음(사실⑤)** |
| `sector_index_daily` | 25테마 지수 31,306행 | 종목 매핑 0 | 2021-01-04 ~ **2026-02-20 정지** | 매핑이 없어 종목과 못 잇는다 |
| `stock_info.sector` | 2,115행 | 0 | — | 전부 빈 문자열 |

⚠️ 어느 표도 「그날 업종」을 모른다 — 백테스트가 현재 라벨을 과거에 끼워 넣게 된다.

### 사실 ②: 결측 239종목의 정체는 우선주와 유니버스 확장분이고, KIS 없이 채울 수 있다

- 239 = DART 회사코드(`dart_corp_code`) 없는 239 와 **같은 집합**(대칭차분 0).
- 우선주 114(코드 끝자리 ≠ '0'): 부모(앞 5자리 + '0')가 KSIC 를 갖는 것 **113/114** — 예외 1 = `0220WL`(부모 `0220W0` 는 상장목록·캐시에 **있으나** `stock_industry` 행이 없다).
- 보통주 형식 125(숫자 69 · 영숫자 56): 회사코드 0 · 123종목이 2026-08 에 처음 일봉이 생겼다(유니버스 확장분 — 상장일 아님).
- `dart_corp_code` 는 2,556행 고정 — `refresh_from_dart()`(corpCode.xml 1호출)가 **어디서도 호출되지 않는다**(grep 0건).
- 🆕 **2026-09-06 실측(corpCode.xml 1회 다운로드, DB 쓰기 없음)**: 상장 3,989건 · **보통주 125 → 125/125 수록** · 우선주 114 → 0/114 · 우선주 부모 114/114 수록. ⇒ KSIC 도달 가능 커버리지 = 2,533 + 125(DART 응답이 전부 `induty_code` 를 준다는 가정) + 우선주 113(즉시) → 114(§6.0-3b 재복사 후 · `0220W0` 이 채워지면) = **2,772/2,772**. ⚠️ 「125 전부 준다」는 08-07 실행(다른 집합, 100%)에서 온 가정이라 **부트스트랩 리포트가 실측으로 대체**한다(§6.0).

### 사실 ③: 성적표는 일봉으로 만들 수 있고, 정의는 이미 동결돼 있다

- 태쏘 `SEC-M1`(`backtest/tasso_program_journal/run_sector.py`): 수익률 = `close / LAG(close) − 1`(`adj_factor` 미적용 · **20 달력일 창 안**의 직전 봉 · 창 안 행도 `close > 0` 조건 `:355-363`), 급등 = `high ≥ prev_close × 1.15`(`UP_MULT` `:123`), 섹터 라벨 = `induty_code` 앞 N자리(`NS=(2,3,5)`, 주 판정 N=3, 길이 < N 이면 미정 `labels_for` `:305`), 섹터 통계 = 중앙값(M1)·급등 수(M2)·상승 비율(M3), 그날 «모든 섹터» 분포 안의 백분위(`rank_pct` `:278-286`, 동률은 `side="left"` = «좋거나 같은»).
- 🔴 **태쏘의 백분위는 «종목별 자기제외(LOO)» 통계다.** 이 스펙의 성적표는 **섹터 수준 «전원» 통계**를 저장한다(§3.2). 같은 명부·같은 수익률 정의·같은 순위 공식이지만 **종목별 `SEC-M1` 값 그 자체는 아니다** — 중앙값은 집계에서 되돌릴 수 없으므로 LOO 가 필요한 소비자는 §3.6 계약대로 멤버에서 다시 계산한다.
- `daily_prices` 는 2021-01-04 부터(거래일 **1,392**, ~2026-09-04 · 술어 유무 무관 동일) ⇒ 백필 가능. `returns_1d` 열은 2026-08 실측에서 불일치 0 이지만 **성적표는 열을 믿지 않고 직접 계산**한다.

### 사실 ④: 접근법 비교 (사장님 확정 = 1)

| | 1. 일봉 계산형 (채택) | 2. KIS 업종지수 수집형 | 3. 최소형 |
|---|---|---|---|
| 업종 성적 출처 | 우리 일봉 | 거래소 공식 지수(시총가중) | 소비자가 매번 계산 |
| 외부 호출 | 캐시 CSV 1회/일 + DART 신규분 | KIS 2,771건/일 + 토큰 공유 | DART 신규분 |
| 세분류(KSIC 3자리) | 가능 | 불가(79업종) | 가능 |
| 검정·라이브 «명부·정의» 일치 | 같은 표 | 정의 다름 | 두 벌 |
| 변경 이력 | 있음 | 없음 | 없음 |

🔑 「같은 업종이 함께 눌렸나」는 **동료 중앙값**의 질문이지 시총 가중 지수의 질문이 아니다.

### 사실 ⑤: FDR 'KRX-DESC' 의 실체 — 79업종이 아니라 «KSIC 소분류 이름»이고, 소스는 GitHub 캐시다

`fdr.StockListing('KRX-DESC')` → `KrxStockListingCache`(`venv/.../FinanceDataReader/data.py:175`): ①KRX 포털 bld 에서 `max_work_dt` 1회 ②**GitHub `FinanceData/fdr_krx_data_cache` 의 `data/listing/desc/{YYYY-MM-DD}.csv`** 를 `pd.read_csv`. KIND 를 직접 긁는 `KrxStockListing` 은 이 경로에서 죽은 코드다. ⇒ 이 스펙은 **FDR 을 부르지 않고 ② 의 CSV 를 날짜 지정으로 직접 읽는다**(§4-①: KRX 포털 호출 0 · 기준일이 명시된다). 실측: `2026-09-03`·`09-04`·`09-05` 파일 전부 HTTP 200(09-06 에 확인). ⚠️ **파일명은 «게시일»이지 «내용 기준일»이 아니다** — 토요일 `09-05.csv` 는 `09-04.csv` 와 **바이트 동일**(md5 `874ee3c0…`). 거래일엔 그날 내용이다(`386380` 상장일 09-04 가 09-03 파일엔 없고 09-04 파일엔 있다). `{D}.csv` 가 D 의 16:00 «전에» 게시되는지는 미확인 → §8-7 이 자기보고한다.

2026-09-04 파일 실측(오프라인 보관 `scratchpad/sector/desc_2026-09-04.csv`, 552,967 bytes):

| 열 | 실제 내용 |
|---|---|
| `Code` `Name` `Market` | 2,873행 = KOSPI 943 · KOSDAQ 1,772 · KONEX 108 · KOSDAQ GLOBAL 50 · 우선주 114 포함 · 영숫자 코드 82 포함 |
| `Sector` | **KOSDAQ 소속부**(중견기업부 511 · 우량기업부 466 · 벤처기업부 340 · 기술성장기업부 255 · 관리종목 128 · 일반기업부 108 · SPAC 65 · 투자주의환기 42 · 외국기업 15) · **KOSPI 943 전부 NULL** — 업종이 «아니다» |
| `Industry` | **KSIC 소분류(3자리) 명칭** 158종 · 우선주 114 는 NULL |
| `Products` `ListingDate` `SettleMonth` `Representative` `HomePage` `Region` | 주요제품(NULL 125) 등 |

🔑 DART `induty_code` 앞 3자리 ↔ `Industry` 를 2,527개 회사로 대조: **158 코드 ↔ 158 이름 · 코드별 지배 이름 점유율 ≥ 0.9 가 158/158 · 행 일치 99.92%**. 이름표에 들어가는 «최빈» 이름은 오늘 단사다(158 코드 → 158 이름 · `474`·`465` 의 겹침은 99.92% 불일치의 잔여 2행). 그래도 화면 라벨은 **「코드 + 이름」**(견고성).
🔴 **KRX 79업종은 자동 갱신 소스가 없다**(pykrx 미설치 · KRX 포털 차단 이력 · KIS 금지) ⇒ 🔒 **사장님 결정(09-06 밤): 분류체계 = KSIC 2·3·5자리로 통일.** 79업종 스냅샷 `stock_sector` 는 그대로 두고 명부·성적표에 넣지 않는다.

---

## 1. 결정 사항

1. **범위 = 공통 기반 둘 다**(명부 + 성적표 + EOD 자동 갱신). 뉴스 집계(스펙 B)·라이브 표시는 별건. — 🔒
2. **접근법 1(일봉 계산형)**. KIS 호출 0. — 🔒
3. **분류체계 = KSIC 2·3·5자리, 이름은 3자리에만(캐시 `Industry` 유래) · 화면 라벨 = 코드+이름.** KRX 79업종은 뺀다. — 🔒(09-06 밤)
4. 매매 룰 0줄 · 라이브 3표(`daily_prices`·`minute_candles`·`virtual_trading_records`) 불변 · EOD 두 줄 · 워크트리 작업 후 EOD 이후 머지. — 🔒
5. 최초 백필 구간은 **현재 스냅샷 소급**임을 명부·이 문서·완료 리포트에 적는다. — 🔒
6. 성적표는 섹터 «전원» 통계이며 태쏘 종목별 LOO 값이 아니다(§3.6). 문서 3 이 LOO 를 쓰면 멤버에서 재계산한다.
7. **부트스트랩과 백필은 머지 «전» 워크트리에서 수동 CLI 로**(재무 백필과 같은 방식 · 야간/주말). EOD 두 줄은 유지만 한다.

---

## 2. 구성요소

| 파일 | 역할 | 비고 |
|---|---|---|
| `collectors/sector_collector.py` | 명부 갱신(캐시 CSV + DART + 우선주 규칙) · 이름표 · 성적표 · CLI `--bootstrap` `--backfill` `--regen` `--regen-map` `--delete-stats` · `reconcile_sector` | 재무 수집기 골격(`collect_*` + summary dict) |
| `collectors/sector_writer.py` | DDL · UPSERT · SCD2 · 함수 · reconcile 행 쓰기(자체 SQL — `financial_writer.upsert_reconciliation` 엔 `real_rows` 인자가 없다) | **DB 쓰기는 이 파일 한 곳뿐** |
| `collectors/krx_desc_cache.py` | GitHub 캐시 CSV 날짜 지정 읽기(+ 7일 후퇴 폴백) · 원본 gz 보관 · 시장별 규모 검증 | FDR 미사용 |
| `collectors/dart_company_fetcher.py` | DART `company.json` 스로틀 클라이언트 | `DartFinancialFetcher`(`min_interval=0.34`, 020/800/blocked) 미러 |
| `collectors/dart_corp_code.py` | 기존. `refresh_from_dart()` 호출자가 생긴다(부트스트랩 + 주 1회) | 코드 변경 없음 |
| `collectors/financial_collector._load_dart_key` | 그대로 import(비공개지만 안정 · 모듈은 EOD 가 이미 import) | 옮기지 않는다 |
| `collectors/eod_collection.py` | `"sector": _safe(collect_sector, trade_date)` · `"sector_reconcile": _safe(reconcile_sector, trade_date)` **2줄, `financials_reconcile` 바로 뒤** | 롤백 = 2줄 제거 |
| `tests/collectors/test_eod_collection.py` | `_stub_flow_stages` 에 `collect_sector`·`reconcile_sector` 추가 | §9 T10 |
| `tests/collectors/test_sector_*.py` | §9 | 전부 red 먼저 |

DB 연결: 읽기·쓰기 모두 `db.kis_db_connection.KisDbConnection`(수집기 관례 · 재무 수집기와 동일 · `require_explicit_target_db` 는 `scripts/*` 전용이라 해당 없음). `daily_prices.date` 는 **text** `YYYY-MM-DD` — 비교는 문자열, 저장은 `date` 형.

**EOD 자리 근거**: opendart 네트워크 호출의 마지막 소비자는 `collect_financials`(`eod_collection.py:57`)이고 `reconcile_financials` 는 DB 만 읽는다. 재무는 020 한 건에도 도달성 FAIL(엄격)이라 **재무가 먼저 쓰게** `financials_reconcile` 뒤에 둔다. 뒤따르는 수급 5단계는 DART 참조 0. DART 공식 일일 한도 20,000건(OpenDART 이용안내 · 미실측) 대비 재무 ≤ 800 + 섹터 ≤ 300.

---

## 3. 스키마 (신규 3테이블 + 이름표 1 + 함수 1)

### 3.1 `stock_sector_map` — 종목 → 업종 명부 (SCD2, 1행 = 종목 × 유효기간)

```sql
CREATE TABLE IF NOT EXISTS stock_sector_map (
    stock_code    varchar(20) NOT NULL,
    valid_from    date        NOT NULL,
    valid_to      date,                       -- NULL = 현재 유효 · 포함(inclusive)
    ksic_code     varchar(10),                -- DART induty_code (현재 길이 3~5 · 5 초과는 WARN 하고 저장)
    ksic_source   text,                       -- 'dart' | 'snapshot_20260807' | 'parent:<보통주코드>' | NULL
    ksic3_name    text,                       -- 캐시 Industry (KSIC 소분류명) · 우선주는 부모 복사
    corp_code     varchar(8),                 -- dart_corp_code 에서 (캐시 CSV 엔 없다)
    market        text,                       -- 캐시 Market (KOSPI/KOSDAQ/KONEX/KOSDAQ GLOBAL)
    kosdaq_dept   text,                       -- 캐시 Sector (KOSDAQ 소속부 · KOSPI NULL)
    products      text,
    listing_date  date,
    settle_month  text,
    source        text        NOT NULL,       -- 'bootstrap_snapshot' | 'eod'
    source_asof   date,                       -- 이 행을 마지막으로 만진 캐시 CSV 의 «게시일»(내용 기준일 ≤ 게시일)
    ksic_checked_at timestamp,                -- 이 종목의 KSIC 를 DART 에 마지막으로 물은 시각 (재확인 순환의 커서 · 스냅샷 행은 NULL 로 시작 · SCD2 새 줄은 닫힌 줄 값을 «승계» · 재확인이 직접 연 줄은 now())
    collected_at  timestamp   NOT NULL DEFAULT now(),   -- 행 생성 시각 · 불변
    last_seen_at  timestamp   NOT NULL DEFAULT now(),   -- 무변경 갱신 때 제자리 갱신 (§8 정체 감지가 읽는다)
    PRIMARY KEY (stock_code, valid_from),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
CREATE INDEX IF NOT EXISTS idx_ssm_open  ON stock_sector_map (stock_code) WHERE valid_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_ssm_asof  ON stock_sector_map (stock_code, valid_from, valid_to);
```

규칙 (전부 «오늘» := `trade_date`, 벽시계 아님)
- **변경 감지 필드 = (`ksic_code`, `ksic3_name`) 둘.** 🔴 **「값 없음」은 변경이 아니다** — 새 값이 NULL/공백이면 그 필드는 «유지». 열린 줄이 NULL 이고 새 값이 있으면 **제자리 채움**(NULL→값은 이력이 아니라 «알게 된 것»). **비-NULL → 다른 비-NULL** 일 때만 열린 줄 `valid_to = trade_date − 1일`, 새 줄 `valid_from = trade_date`.
- 열린 줄 `valid_from == trade_date` 이면 값→값 변경도 **제자리 갱신**(PK 충돌·역전 방지). 열린 줄 `valid_from > trade_date` 이면(과거 날짜 재실행) **그 종목은 건너뛰고 건수를 WARN** — CHECK 가 역전을 막는다.
- 부수 열(`corp_code`·`market`·`kosdaq_dept`·`products`·`listing_date`·`settle_month`·`source_asof`·`last_seen_at`)은 항상 제자리 갱신. `collected_at` 불변.
- **부트스트랩**(§6.0): `valid_from='2021-01-04'`, `source='bootstrap_snapshot'`, KSIC 는 `stock_industry` 에서 `ksic_source='snapshot_20260807'`, 이름·부수 열은 그날 캐시 CSV. `stock_industry` 는 **부트스트랩에서만** 읽는다. 그 뒤 처음 보는 종목은 `valid_from = trade_date`, `source='eod'`.
- 🔴 **부트스트랩 행에 대한 이후 DART 제자리 채움(`ksic_source='dart'`)도 소급이다**(`valid_from=2021-01-04` 이므로 과거 날짜 조회에 그대로 보인다). 소급 판별은 **행의 `source='bootstrap_snapshot'`** 로 한다(`ksic_source` 가 아니라).
- 상장폐지·캐시에서 사라짐은 줄을 닫지 않는다. 닫는 건 «값→값 업종 변경»뿐.
- **우선주 규칙**(코드 끝자리 ≠ '0'): 부모 = 앞 5자리 + '0'. 부모가 U_all 에 있으면 필드별로 복사한다 — `ksic_code`·`corp_code` 는 **부모가 `ksic_code` 를 가질 때만**(`ksic_source='parent:<부모코드>'`), `ksic3_name` 은 **부모가 이름을 가질 때**(KSIC 와 독립 · 캐시엔 114/114 부모 이름이 있다). 부모가 없으면(가상의 `0220XL`) 전부 NULL · 부모는 있으나 KSIC 가 없으면(실제 `0220WL` → `0220W0`) 코드만 NULL. 캐시 행의 자기 값(우선주는 `Industry` NULL)이 있으면 그것이 우선. `0220W0` 자체가 DART 채우기 대상(125 중 하나)이므로 부트스트랩은 DART 채우기 «뒤에» 우선주 복사를 한 번 더 돌린다(§6.0-3b) — 그래서 부트스트랩 리포트 기대치는 2,772/2,772 다.
- 🔴 **소스 급변 가드**(필드별): 분자 = «비-NULL → 다른 비-NULL» 변경 종목 수 · 분모 = 열린 줄 중 그 필드가 비-NULL 인 수 · 분모 0 이면 생략. 어느 필드든 **5% 초과면 한 행도 쓰지 않는다**(RuntimeError). NULL 채움·신규 종목은 분자에 안 들어간다.
- 트랜잭션: §4 의 ①②③④ 는 **각각 별도 트랜잭션**. ④(이름표) 실패가 ①~③ 을 되돌리지 않는다.

### 3.2 `sector_daily_stats` — 업종 일별 성적표 (1행 = 날짜 × 분류체계 × 업종)

```sql
CREATE TABLE IF NOT EXISTS sector_daily_stats (
    date         date        NOT NULL,
    taxonomy     text        NOT NULL CHECK (taxonomy IN ('ksic2','ksic3','ksic5')),
    sector_key   text        NOT NULL,
    CHECK ((taxonomy='ksic2' AND sector_key ~ '^[0-9]{2}$') OR (taxonomy='ksic3' AND sector_key ~ '^[0-9]{3}$') OR (taxonomy='ksic5' AND sector_key ~ '^[0-9]{5}$')),
    n_members    int         NOT NULL,        -- 그날 r 이 유한한 소속 종목 수
    g_sectors    int         NOT NULL,        -- 그날 taxonomy 안에서 n_members>=1 인 업종 수 (=G)
    ret_median   double precision,            -- M1 · 전원 중앙값
    ret_mean     double precision,
    up_count     int,                         -- M2 · high >= prev_close*1.15 인 종목 수
    pos_ratio    double precision,            -- M3 · r>0 비율
    rank_median  int,  pct_median double precision,   -- M1 의 섹터간 순위·백분위
    rank_up      int,  pct_up     double precision,   -- M2 (⚠️ 대개 동률 — 아래)
    rank_pos     int,  pct_pos    double precision,   -- M3
    computed_at  timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (date, taxonomy, sector_key)
);
CREATE INDEX IF NOT EXISTS idx_sds_tax_date ON sector_daily_stats (taxonomy, date);
```

계산 정의 (태쏘 `run_sector.py` 의 «전원» 통계와 순위 공식을 따른다 · 차이는 명시)
- 대상 행: `daily_prices` 에서 **창 `date BETWEEN d−20달력일 AND d` 안의 행 전부에 `config.constants.SQL_STOCK_ONLY` ∧ `close > 0`** 를 걸고, 종목별 `LAG(close)` 로 `prev_close` 를 구한 뒤 `date = d` 행만 남긴다(태쏘 `load_day` 와 같은 순서 · 창 안에 직전 봉이 없으면 `r` 미정 → 제외·건수 집계). ⚠️ 태쏘의 `market_cap > 0` 조건은 **넣지 않는다**. 🔴 시총은 사실상 2024-03-13 부터만 있다(첫 비-NULL 2023-04-25 · 그 전 월 0~176행 vs 이후 월 3~5만 행) ⇒ **2021-01-04 ~ 2024-03-12(백필 구간의 약 55%)에서는 태쏘 SEC-M1 과 «비교 자체가 불가»**(태쏘 유니버스가 거의 빈다). 이 구간의 성적표는 태쏘와 대조되지 않은 채 «정의만 같다» — T9 는 2026-08-05 한 날짜만 재고, 이 사실은 §5-2 와 완료 리포트에 같이 적는다. 의사티커는 술어가 뺀다(실측: 숫자로 시작하지 않는 코드 = `KOSPI`·`KOSDAQ`·`KQ11`·`KS11` 넷뿐).
- `r = close / prev_close − 1` · `up = high ≥ prev_close × 1.15`.
- 라벨: `fn_sector_map_as_of(d)` 조인 → `ksic2 = left(ksic_code,2)` · `ksic3 = left(,3)` · `ksic5 = left(,5)`. **길이 < N 이거나 접두가 숫자가 아니면 그 taxonomy 에서 미정**(태쏘 `labels_for` · 비숫자는 실측 0건이지만 CHECK 위반으로 ③ 이 죽지 않게) → 제외·건수 집계. 실측 키 공간: ksic2 61 · ksic3 161(2026-08-05 성적표 159) · ksic5 327(5자리 코드 회사 1,186 — 나머지 1,370 은 ksic5 미정). 현재 길이 분포는 3/4/5 뿐(길이 < 3 은 0건).
- 순위·백분위(세 통계량 각각): `G` = 그날 `n_members ≥ 1` 인 업종 수. `rank_x` = **자기 제외, 통계량이 «좋거나 같은»(≥) 다른 업종 수**(동률 포함 = 태쏘 `rank_pct` `side="left"`). `pct_x = 100·(G−1−rank_x)/(G−1)` · `G < 2` 면 NULL.
- ⚠️ **`rank_up`/`pct_up` 은 대개 동률이다** — 2026-08-05 실측 129/159 업종이 `up_count=0`(고유값 9개) ⇒ `pct_up=0` 은 「최하위」가 아니라 「대다수와 동률」. 소비자는 `up_count` 원값과 `n_members` 를 함께 봐야 한다. 주 소비자(문서 3)는 M1 만 쓴다.
- `n_members < 3` 인 업종도 저장한다. 문턱(문서 3 의 N≥3)은 소비자 몫이다.
- 미정 종목 수(라벨 없음 · 길이 부족 · prev_close 창 밖)는 summary dict 와 로그에 남긴다(무징후 절단 금지).

### 3.3 `sector_ksic_nodata` — DART 가 「업종 없음」이라고 답한 종목

```sql
CREATE TABLE IF NOT EXISTS sector_ksic_nodata (
    stock_code  varchar(20) PRIMARY KEY,
    checked_at  timestamp   NOT NULL DEFAULT now()
);
```
`company.json` 응답에 `induty_code` 가 비어 있으면 기록(이미 있으면 `checked_at` 을 지금으로 갱신 — 30일 뒤 또 재시도하도록). **`checked_at` 이 30일 지나면 다시 두드린다**(재무 백필 082660 교훈: 「없다」는 답도 틀릴 수 있다).

### 3.4 `ksic_code_name` — KSIC 3자리 이름표 (데이터에서 생성)

```sql
CREATE TABLE IF NOT EXISTS ksic_code_name (
    level       int         NOT NULL CHECK (level = 3),
    code        varchar(5)  NOT NULL CHECK (code ~ '^[0-9]{3}$'),
    name        text        NOT NULL,
    n_stocks    int         NOT NULL,         -- 이 (code,name) 쌍을 가진 «종목» 수 (부모복사 우선주 포함)
    share       double precision NOT NULL,    -- 그 code 안에서 이 name 의 점유율
    built_at    timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (level, code)
);
```
매 EOD ④ 에서 열린 줄 중 **`ksic_code IS NOT NULL AND length(ksic_code) >= 3 AND ksic3_name IS NOT NULL`** 만으로 `(left(ksic_code,3), ksic3_name)` 최빈 이름을 재생성(2026-09-04 실측 158/158 코드 점유율 ≥ 0.9). 점유율 < 0.8 인 코드는 WARNING. 2·5자리 이름은 범위 밖. ⚠️ **이름표는 PIT 가 아니다**(매일 재생성 · 표시 전용) — 과거 성적표와 조인해도 «오늘 이름»이 붙는다.

### 3.5 실사례 — 2026-08-05 · `ksic3` (관리자 재계산 · critic 2차 독립 재현 일치 · 명부 대신 `stock_industry` · 20일 창 · 대상 행 2,763 · G = 159)

| code | 이름(캐시 Industry) | n | ret_median | up_count | pos_ratio | rank_median | pct_median |
|---|---|---:|---:|---:|---:|---:|---:|
| 261 | 반도체 제조업 | 71 | +5.670% | 11 | 0.930 | 1 | 99.4 |
| 311 | 선박 및 보트 건조업 | 13 | +5.029% | 0 | 0.923 | 5 | 96.8 |
| 264 | 통신 및 방송 장비 제조업 | 60 | +4.053% | 10 | 0.867 | 7 | 95.6 |
| 641 | 은행 및 저축기관 | 5 | +0.998% | 0 | 0.600 | 84 | 46.8 |
| 212 | 의약품 제조업 | 103 | +0.494% | 2 | 0.689 | 112 | 29.1 |

읽는 법: 반도체 제조업은 71종목 중앙값 +5.67% 로 159개 업종 중 «좋거나 같은» 업종이 1개(자기 제외) → 백분위 99.4. ma20 눌림 후보가 261 소속이었다면 「업종이 같이 눌렸다」가 **아니다**(오히려 급등).

### 3.6 `fn_sector_map_as_of(p_as_of date)` — 그 날짜의 명부 (1행 = 종목) · 소비자 계약

```sql
CREATE OR REPLACE FUNCTION fn_sector_map_as_of(p_as_of date)
RETURNS TABLE (stock_code varchar(20), ksic_code varchar(10), ksic_source text, ksic3_name text, valid_from date, source text)
LANGUAGE sql STABLE AS $$
    SELECT stock_code, ksic_code, ksic_source, ksic3_name, valid_from, source
    FROM stock_sector_map
    WHERE valid_from <= p_as_of AND (valid_to IS NULL OR p_as_of <= valid_to)
$$;
```
- 반환 타입은 컬럼 타입과 자리수까지 같게. T11 이 `SELECT * FROM fn_sector_map_as_of(d)` 왕복과 **종목당 ≤ 1행**(임의 날짜 표본)을 확인.
- 소비자 계약: ①문서 3·태쏘식 LOO 는 이 함수로 라벨을, `daily_prices` 로 `r` 을 가져와 **자기 코드로 재계산**한다(성적표 `pct_median` 은 전원 통계). ②NewsQuant 는 `news.related_stocks` → `fn_sector_map_as_of(공시일)` → `ksic3` → `sector_daily_stats` 조인(스펙 B). ③라이브 표시는 당일 `sector_daily_stats` + `ksic_code_name`(라벨 = 코드+이름).
- `source='bootstrap_snapshot'` 행은 소급 라벨이다(§5-2). 부트스트랩 이전 날짜는 빈 결과.

---

## 4. 데이터 흐름 (EOD, 매일 16:00 · `financials_reconcile` 뒤)

```
캐시 CSV(GitHub · trade_date 지정 · ≤7일 후퇴) ─┐
stock_industry(부트스트랩만) ───────────────────┼─ ① 명부 갱신 ──► stock_sector_map ──► ④ ksic_code_name
DART corpCode.xml(주 1회) ─────────────────────┤
DART company.json(≤300/일) ────────────────────┘ ② KSIC 채우기 (corp_code 有 ∧ ksic 無 ∧ nodata 30일 경과)
daily_prices(그날) ─── ③ 성적표 ── fn_sector_map_as_of(그날) ──► sector_daily_stats (ksic2·3·5)
```

① 명부 갱신 (`krx_desc_cache.py`)
1. `https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/refs/heads/master/data/listing/desc/{trade_date}.csv` 를 읽는다. 404 면 하루씩 최대 7일 후퇴(실제 읽은 파일의 날짜 = **`source_asof`** = «게시일» · 내용 기준일은 그 이하 · summary·행·보관 파일명 `RoboTrader_template/scratchpad/sector/krx_desc_{source_asof}.csv.gz` 에 남긴다 · 레포 루트 `scratchpad/` 와 다르다). 7일 안에 없으면 실패. 주말 게시분은 금요일 내용과 동일하므로 주말 부트스트랩은 `source_asof` = 그날, 내용 = 직전 거래일이다(정상). `source_asof < trade_date` 가 «매일» 반복되면 게시가 16:00 뒤라는 뜻 → §8-7.
2. 검증: 0건 → 실패 · `Code` 6자리 정규화 · **규모 하한**: `Market ∈ {KOSPI}` 와 `{KOSDAQ, KOSDAQ GLOBAL}` 두 묶음 각각 기존 열린 줄 대비 80%(`stock_market_collector._check_scale_floor` 와 같은 모양 · 기존 0 이면 면제) · KONEX 는 U_all 밖이라 검증·적재 대상 아님 · 소형 세그먼트(GLOBAL 50)는 KOSDAQ 묶음에 합쳐 30건 오차로 흔들리지 않게 한다. ⚠️ 기준선(열린 줄)은 상폐로 줄지 않으므로 약 6년 뒤 정상 수집도 거부될 수 있다 — `stock_market_collector` 와 같은 «소리 나는» 한계(그때 기준을 다시 잡는다).
3. U_all 각 종목의 후보 값: **보통주** — `ksic_code`(열린 줄 값 → 부트스트랩 때만 `stock_industry` → NULL) · `ksic3_name`(캐시 `Industry` → NULL) · `corp_code`(`dart_corp_code` → NULL). **우선주** — 세 값 모두 **부모 규칙이 열린 줄 값보다 우선**(부모가 바뀌면 자식도 그날 바뀐다 · §3.1 값→값 규칙으로 새 줄) · 부모에 값이 없으면 열린 줄 값 유지. 그 외 부수 열(캐시).
4. §3.1 변경 감지 → 급변 가드 → SCD2 쓰기(한 트랜잭션).

② KSIC 채우기
- 주 1회(`dart_corp_code.max(updated_at)` 이 7일 이상 지났으면 · 휴장 무관): `refresh_from_dart()`(1호출 · 3,989건 upsert — 유니버스 밖 행이 늘지만 재무 수집기는 교집합만 쓴다 → 무해 · 재무 「미매핑 239」 백로그도 풀린다).
- 매일 (a) **채우기**: 열린 줄 중 `corp_code IS NOT NULL AND ksic_code IS NULL` 이고 nodata 30일 미경과가 아닌 종목(`ksic_source LIKE 'parent:%'` 행은 제외 — 부모 코드로 자식을 묻지 않는다) → `company.json`. `induty_code` → `ksic_source='dart'`, `ksic_checked_at=now()`.
- 매일 (b) 🔴 **재확인 순환**(v5 · 코드가 «쓰기 한 번»으로 굳지 않게): (a) 를 뺀 잔여 예산으로 `ksic_source IN ('dart','snapshot_20260807')` 인 열린 줄을 `ORDER BY ksic_checked_at ASC NULLS FIRST` 로 **최대 200건** 다시 묻는다. 응답 코드가 다르면 §3.1 의 값→값 규칙(새 줄 · `ksic_checked_at=now()`) · 같으면 `ksic_checked_at` 만 갱신 · 비어 있으면 무시(값 없음 = 변경 아님). 대상 풀 ≈ 2,658(부모복사 114 제외) → 한 바퀴 ≈ **13~14 거래일**. 🔴 **재확인 전용 레일**: 그날 재확인 응답 중 값→값이 **20% 초과 또는 30건 초과**면 그날 재확인 분을 **전부 롤백**하고 RuntimeError(§3.1 의 5% 가드는 분모가 전체 열린 줄이라 200건 표본에선 139건이 바뀌어야 걸린다 — 표본 기준 레일이 따로 필요). 응답 원문은 `scratchpad/sector/dart_company_{YYYY-MM-DD}.jsonl` 로 보관(§5-4 재생성 원료).
- 매일 (c) **우선주 재복사** — (a)(b) 로 부모가 바뀐 자식을 받는다(§6.0-3b 의 EOD 판).
- 공통: `min_interval=0.34` · **하루 총 상한 300건** ≈ 102초 · 020/blocked 즉시 중단 · summary `ksic_fill` 에 `fill_calls`·`recheck_calls`·`recheck_changed` 를 따로 센다. `ksic_source IS NULL` 인 열린 줄(부모도 DART 도 없음)은 (a) 의 `corp_code` 조건과 `sector_ksic_nodata` 30일 재시도가 덮는다 — 그 밖의 영구 미라벨은 §8-1 미라벨 목록으로 드러난다.

③ 성적표 — 그날 `daily_prices` 0행이면 스킵(휴장일 정상 · WARNING). 있으면 §3.2 → UPSERT.
🔴 **실패 경로**: ①이 실패(캐시 404·규모 하한·급변 가드 등 RuntimeError)해도 `collect_sector` 가 **안에서 잡고** ②③④ 를 계속 돌린다 — `_safe` 까지 올라가면 summary 가 안 써져 §8-5 가 그날을 못 본다. summary 는 **어떤 경우에도 쓴다**(`map.written=false` + 사유). `_safe` 는 최후 방어선일 뿐이다.
④ 이름표 — §3.4 재생성.

summary: `{"map": {"source_asof", "open_rows", "changed", "filled", "new", "skipped_past", "null_rate": {"ksic_code","ksic3_name"}(분모 = U_all 과 매칭된 캐시 행), "guard": {...}, "written": bool}, "corp_code_refreshed": bool, "ksic_fill": {"fill_calls", "recheck_calls", "recheck_changed", "filled", "nodata", "status_counts"}, "stats": {"date", "rows", "G": {...}, "undefined": {"no_label","short_code","no_prev"}}, "names": {"codes", "low_share"}}`.
🔴 **이 summary 는 `RoboTrader_template/scratchpad/sector/sector_summary_{YYYY-MM-DD}.json` 으로 매일 저장한다**(날짜는 ISO · gz 파일명도 같다)(재무 수집기 `_write_summary` 와 같은 방식) — §8 의 «전일 대비»·«N일 연속» 게이트는 이 파일들을 읽는다. 저장이 없으면 그 게이트들은 «한 번도 발동 안 함»이 된다.

---

## 5. 🔴 시점(PIT) 규칙

1. 성적표는 **그날 유효한 명부**(`fn_sector_map_as_of(그날)`)만 쓴다. 이후 명부가 바뀌어도 과거 행은 자동 재계산하지 않는다.
2. **부트스트랩 행(`source='bootstrap_snapshot'`, 2021-01-04 ~ 구축일)은 현재 스냅샷의 소급**이다 — 그 행에 나중에 DART 로 채운 KSIC(`ksic_source='dart'`)도 마찬가지다. 이 구간을 쓰는 문서(문서 3 등)는 판정문에 인쇄한다. 편향 크기는 재지 않는다(§10) — 완료 리포트(§11)에도 같은 문장을 적는다. **같은 자리에 「2024-03-12 이전 성적표는 태쏘 SEC-M1 과 대조되지 않았다」(§3.2)도 적는다.**
3. 업종을 모르는 종목은 **fail-closed** — 빼고 건수를 남긴다.
4. 명부 **손 수정 금지**(SQL 직접 UPDATE/DELETE 금지). 잘못된 줄은 ①소스 원인 수정 ②`--regen-map --from <date>`(그 날짜 이후의 SCD2 를 보관 gz + `dart_company_*.jsonl` 로 재생성 · **하한 = 첫 EOD 날짜** — 부트스트랩 행은 gz 가 아니라 `stock_industry`(동결) + 부트스트랩 날 gz 로 재현 · 캐시 CSV 엔 코드 열이 없으므로 `ksic_code`·`ksic_source`·`ksic_checked_at` 은 jsonl 보관분으로만 재생성하고 보관분이 없는 구간은 **보존**한다) ③`--regen --from --to` 성적표 재계산 ④리포트. 전부 사장님 승인 후. 보관 gz(`scratchpad/sector/`, gitignore 대상)는 **삭제 금지**이며 유실 시엔 업스트림 GitHub 저장소의 커밋 이력에서 같은 날짜 파일을 다시 받는다(공개 저장소 · 이력 보존).
5. `--bootstrap`·`--regen`·`--backfill`·`--regen-map`·`--delete-stats` 는 **평일 15:30~17:00 거부**(`--force` 없이는) · 전부 `--dry-run` 을 지원한다(쓰기 0 · 리포트만). EOD 의 과거 날짜 재실행(`run_data_collection('YYYYMMDD')`)은 명부에 대해 §3.1 「`valid_from > trade_date` 건너뛰기」로 보호된다.

---

## 6. 스케줄 · 부트스트랩 · 백필

### 6.0 부트스트랩 (1회 · 머지 전 · 워크트리에서 · 야간/주말 · 사장님 승인 후)
`python -m collectors.sector_collector --bootstrap --date <YYYY-MM-DD>` 순서:
1. `refresh_from_dart()` — corpCode.xml 1호출(3,989건).
2. 명부 부트스트랩 — `stock_industry`(2,556) + 캐시 CSV(`--date`) + 우선주 규칙 → `valid_from='2021-01-04'`, `source='bootstrap_snapshot'`. **이 시점 도달 커버리지 = 2,533 + 113 = 2,646/2,772 = 95.5%**(아직 98% 아님 — 정상).
3. DART `company.json` 으로 `corp_code` 있고 KSIC 없는 종목(예상 125) 채우기 — 부트스트랩에서는 상한 300 그대로(125 < 300).
3b. **우선주 복사를 한 번 더** — 3 에서 부모(`0220W0` 등)가 채워진 자식을 받는다. 기대치 = **2,772/2,772**.
4. 이름표 생성.
5. **부트스트랩 리포트** `RoboTrader_template/scratchpad/sector/bootstrap_report_<stamp>.txt`: U_market 대비 `ksic_code`·`ksic3_name` 커버리지(3 단계 «후») · **미라벨 종목 목록** · DART 125 응답 실측(`000`/`013`/nodata 건수) · 이름표 코드 수·점유율 < 0.8 목록 · 라이브 3표 전후.
6. 🔴 **게이트**: 두 커버리지(`ksic_code`·`ksic3_name`) 중 **하나라도 < 98%** 면 여기서 멈추고 사장님께 보고(백필 진행 안 함). 예상 = 코드 100%(3b 후) · 이름 99.75%(critic 3차 실측). `--dry-run` 으로 먼저 돌려 리포트만 본다.

> ✅ **실측 (Task 14 · 2026-09-07 18:29~18:30 실행 · `--date 2026-09-07` · `--force` 없음)** — 아래가 실행 리포트
> `RoboTrader_template/scratchpad/sector/bootstrap_report_20260907_183018.txt` 의 값이다. 위 스펙 문장은 손대지 않았다.
>
> | 스펙 자리 | 예상 | **실측** | 비고 |
> |---|---|---|---|
> | §6.0-1 corpCode.xml | 3,989건 | **3,989건** | 갱신 «전» `dart_corp_code` 는 2,556행이었다 — 이 실행이 `refresh_from_dart` 의 첫 호출자다 |
> | §6.0-2 「이 시점 도달 커버리지 = 95.5%」 | 2,646/2,772 = 95.5% | **`ksic_code` 0.954545 · `ksic3_name` 0.997475**(U_market 2,772) | 일치 |
> | §6.0-2 명부 쓰기 | — | `inserted` **2,795** · `closed`/`updated`/`changed` 0 · `written` true · `source_asof` 2026-09-07 · `stale` false · `no_csv` **30** · KONEX **108** 무시 | U_all 2,795 |
> | §6.0-3 「예상 125」 | 125 | **`fill_targets` 125 · `fill_calls` 125 · `filled` 125** | 일치 · 상한 300 미도달(`cap_hit` false) |
> | §6.0-3b 「기대치 2,772/2,772」 | 100% | **`ksic_code` 1.0 = 2,772/2,772 · `ksic3_name` 0.997475** | 우선주 재복사 `filled` 1 · `unchanged` 113 |
> | §6.0-5 「DART 125 응답 실측(000/013/nodata)」 | — | **`{'000': 125}` · 013 0건 · nodata 0 · `fetch_failed` 0** | 전건 정상응답 |
> | §6.0-5 「이름표 코드 수·점유율<0.8」 | ≥155 | **`codes` 158 · `low_share` []**(0건) | |
> | §6.0-5 미라벨 목록 | — | **7종목**: 031440·043090·082640·096610·269620·299900·471050 | 전부 `ksic3_name` 결측(`ksic_code` 는 100%) |
> | §6.0-6 게이트 | 둘 다 ≥98% | **통과**(1.0 · 0.997475) | |
> | §10 라이브 3표 | 불변 | **전 == 후**: 3,189,105 / 60,444,711 / 1,588 | KIS 호출 0 · DART 호출 126(corpCode 1 + company 125) ≤ 300 |
>
> 🔴 **dry-run 예측은 첫 실행에서 「예상 125 → 실측 0」으로 어긋났다**(리포트 `bootstrap_report_dryrun_20260907_182825.txt`).
> 원인은 규명됐다: `would_dart` 는 **corp_code 가 있는** 종목만 세는데, dry-run 은 1단계(`maybe_refresh_corp_code`)를
> 돌지 않아 갱신 «전» 매핑(2,556행 = `stock_industry` 와 동일 집합)만 본다. 그래서 채워야 할 125종목이 전부
> 「물을 수단이 없는」 상태로 보였고 3b 후 커버리지 예측도 95.45% 로 **과소**하게 나왔다(실측 100%).
> ⚠️ 부록 E-4 는 이 예측을 「**과대**일 수 있다」고 적었으나 첫 실행의 실제 방향은 **과소**였다 —
> **첫 실행(= corp_code 갱신 전)에서 dry-run 커버리지 예측은 어느 방향으로든 신뢰할 수 없다.**

### 6.1 EOD
- 자리: `run_data_collection` 의 `"financials_reconcile"` **바로 뒤**. 소요: 캐시 CSV 수 초 + DART ≤ 102초 + 성적표 수 초 + 이름표 1초.
- 발효: 머지 후 다음 **07:40 재기동** 뒤 첫 16:00 EOD. 첫 EOD 는 «유지» 실행이다(부트스트랩·백필은 §6.0·§6.2 에서 이미 끝나 있다).

### 6.2 백필 (1회 · 부트스트랩 게이트 통과 후 · 야간/주말)
- `python -m collectors.sector_collector --backfill --from 2021-01-04 --to <어제>`: 거래일 순회 · **첫날 2021-01-04 는 20일 창 안에 직전 봉이 없어 성적표가 비므로 결과는 1,391일**(거래일 1,392 − 1) · 일자당 (ksic2 ~61 + ksic3 ~159 + ksic5 ~327) ≈ 550행 → **약 76만 행**. pandas 벡터 · `execute_values` 배치 · 예상 수 분. 라이브 3표 읽기만. 성적표는 명부+일봉에서 **수 분이면 전부 재생성**되므로 스키마 변경은 마이그레이션이 아니라 재계산이다.
- 보고서: `RoboTrader_template/scratchpad/sector/backfill_report_<stamp>.txt` — 범위 · 행수 · 일자별 G 분포 · 미정 종목 수 분포 · 라이브 3표 전후 · **「2021~구축일 라벨은 현재 스냅샷 소급」 문장**.
- **데이터 롤백**: `--delete-stats --from --to [--taxonomy]` 가 `DELETE FROM sector_daily_stats …` 를 건수와 함께 리포트에 남기고 실행(승인 필수).

> ✅ **실측 (Task 14 · 2026-09-07 18:31:16~18:44:11 실행 · `--from 2021-01-04 --to 2026-09-07` · `--force` 없음)** —
> 실행 리포트 `RoboTrader_template/scratchpad/sector/backfill_report_20260907_184411.txt` 의 값이다. 위 스펙 문장은 손대지 않았다.
>
> | 스펙 자리 | 예상 | **실측** | 비고 |
> |---|---|---|---|
> | §6.2 「약 76만 행」 | ≈760,000 | **727,674행** | 「예상 76만 → 실측 72.8만」(−4.3%) · ksic2 84,463 + ksic3 219,110 + ksic5 424,101 |
> | §6.2 「예상 수 분」 | 수 분(부록 E-3 은 「수 분~15분 · **추정**」) | **`elapsed_sec` 775.03초 = 12분 55초** | **첫 실측이다** — 15분 미만이라 창 SQL 재작성은 하지 않았다 |
> | §6.2 「1,391일」 | 거래일 1,392 − 1 | **`days_with_rows` 1,392**(거래일 `days` **1,393** − 1) | 「예상 1,391 → 실측 1,392」 — 스펙이 쓴 거래일 1,392 자체가 낡았다(`--to` 가 2026-09-07 로 하루 늘어 1,393) · **「−1」 관계는 그대로 성립** |
> | §6.2 빈 첫날 | 2021-01-04 | **2021-01-04 성적표 0행**(입력 1,766행 · `no_prev` 1,766) | 창 안에 직전 봉이 없어서 — 설계대로 · 삭제도 하지 않았다(유효 행 보호) |
> | 일자별 G 분포 | ksic2 ~61 · ksic3 ~159 · ksic5 ~327 | **ksic2 중앙값 61(max 61) · ksic3 중앙값 157(max 161) · ksic5 중앙값 302(max 327)** | min 은 셋 다 0 — 아래 2026-01-11 참조 |
> | §10 라이브 3표 | 불변 | **전 == 후**: 3,189,105 / 60,444,711 / 1,588 | 읽기만 |
> | 완료 판정(§11-3) | `stats_days = daily_days − 1` | **1,392 = 1,393 − 1** ✅ (`date <= '2026-09-07'` 로 잘라 측정) | `dups` 0 · `ksic_code_name` 158 |
>
> 🔑 **`ksic5` 만 1,391일이다**(ksic2·ksic3 는 1,392일). 빠진 날은 **2026-01-11(일요일)** 하나이며, 그날
> `daily_prices` 에 **`005930` 단 1행**(close 68,500 · volume 1,200,000)만 있어 5자리 라벨이 하나도 만들어지지
> 않았다(`short_code.ksic5` 1 · `G.ksic5` 0). 코드는 설계대로 **그 taxonomy 만 「계산 0행 → 삭제 건너뜀」**
> 으로 처리하고 WARNING 을 남겼다(최종 리뷰 M-b 판정의 첫 실증):
> `[sector] 2026-01-11 ksic5 taxonomy 계산 0행 - 삭제 건너뜀 · 기존 행 보존` · `삭제={'ksic2': 0, 'ksic3': 0, 'ksic5': None}`.
> ⚠️ **이 1행은 이 프로젝트가 만든 게 아니라 `daily_prices` 에 원래 있던 이상 행이다** — 2021-01-04~2026-09-07
> 전체에서 하루 행수가 10 미만인 날은 이 하루뿐이고(전후 거래일은 2,488행), 일요일이라 거래일이 아니다.
> 섹터 쪽 결함이 아니므로 여기서는 고치지 않고 **관측만 남긴다**(별건 백로그).

### 6.3 범위 밖
2·5자리 KSIC 이름(통계청 분류표) · KRX 79업종 갱신 소스 탐색.

---

## 7. 에러 처리

| 상황 | 동작 |
|---|---|
| 캐시 CSV 7일 연속 404 · 0건 · 규모 하한 미달 · 급변 가드 · `valid_from > trade_date` 대량 | 명부 **안 씀**(어제 명부 유지 · `written=false`) · 성적표는 진행 · ERROR 1줄 · §8-5 가 연속 일수를 센다 |
| 캐시 CSV 는 있으나 `source_asof < trade_date − 5거래일` | 명부 갱신은 하되 summary 에 `stale=true` · §8-6 WARN |
| DART 020(한도)·blocked | KSIC 채우기 중단 · 나머지 진행 · summary status |
| DART 800(점검)·HTTP 실패 | 백오프 재시도(재무 fetcher 동일) · 소프트 실패 집계 |
| 그날 `daily_prices` 0행 | 성적표 스킵 · WARNING(휴장일 정상) |
| `ksic_code` 길이 > 5 응답 | 저장하되 WARN(현재 0건 · varchar(10)) |
| `fn_sector_map_as_of` 0행 | 성적표 스킵 · ERROR(부트스트랩 전) |
| 부트스트랩 게이트 < 98% | 백필 진행 안 함 · 보고 · 결정 대기(§6.0-6) |
| 오늘 `sector_summary_*.json` 없음(`collect_sector` 가 `_safe` 까지 터짐) | §8 에서 WARN · **3거래일 연속이면 FAIL**(재무 `no_summary` 와 같은 규칙) |
| 어떤 예외든 | `_safe` 가 잡아 `{"error": ...}` — 다른 단계를 막지 않는다 |

🔑 「0건」에는 두 종류가 있다 — 미정·스킵·`written=false` 를 **항상** 인쇄해 「안 돌았다」와 「돌았는데 0」을 가른다.

---

## 8. reconcile (건강 판정) — `reconcile_sector(trade_date)`

오늘 summary(§4) 와 **직전 N일의 `sector_summary_*.json`**(없으면 그 게이트는 «이력 부족»으로 PASS 하되 사유 인쇄 — 첫 EOD 가 그렇다) 과 DB 를 보고(전부 **U_market 소속 열린 줄**만 센다 — U_all 의 상폐 23 은 분자·분모 모두 제외):
1. `ksic_code` 비-NULL ≥ U_market × 0.98 · `ksic3_name` 비-NULL ≥ U_market × 0.98.
2. 성적표 그날 행 존재(휴장일 제외) · `ksic2` G ≥ 40(키 61) · `ksic3` G ≥ 100(키 161·실측 159) · `ksic5` G ≥ 200(키 327·2026-08-05 실측 324) — 급감은 조인 붕괴 신호 · **전일 대비 ±20% 밖이면 WARN**(급증 = 잘못된 코드 주입으로 파편화).
3. 미정 `no_label` 이 전일 대비 +50 이상이면 WARN · **`no_prev` > max(20, 3 × 직전 20거래일 `no_prev` 중앙값) 이면 WARN**(일봉 결손 신호). 기저 실측 2026-07-27~09-04: 0~3건/일(중앙값 0) · 유일한 예외 2026-08-05 = 189(유니버스 확장분 123종목 첫 일봉 — 알려진 이상치). 「전일의 2배」 규칙은 쓰지 않는다(기저 0 에서 1건이 걸린다).
4. **정체**: `new_rows`(= `corp_code` 있고 `ksic_code` NULL 인 수 · 아래 recon 행에서 읽는다 — 재무와 같은 방식)가 **> 0 이고** 3거래일 연속 같으면 WARN(0=0=0 은 정상 — 채울 게 없는 것) · **`recheck_calls` 가 20거래일 연속 0 이면 WARN**(재확인 순환 정지 의심) · **`recheck_changed` > 10 이면 WARN**(레일 아래에서도 보이게). 재무의 정체는 FAIL 이지만 여기선 WARN — 재무는 창(35일) 안에 못 받으면 영영 못 받지만 KSIC 는 다음 날 또 물을 수 있다.
5. 🔴 **얼어붙은 명부**: `map.written=false` 가 **2거래일 연속**이면 FAIL · `max(last_seen_at)` 이 `trade_date − 3거래일` 보다 오래됐으면 FAIL(「값 없음은 변경 아님」 규칙이 만든 사각 — 소스가 통째로 NULL 이 돼도 커버리지 게이트는 통과하기 때문).
6. **소스 이상**: 적재 대상(U_all 매칭) 행의 필드별 NULL 비율이 전일의 2배 초과 또는 10% 초과면 WARN · `stale=true` 면 WARN.
7. **게시 지연**: `source_asof < trade_date` 가 거래일 3일 연속이면 WARN(캐시가 16:00 뒤에 게시된다는 뜻 → EOD 자리·후퇴 규칙 재검토).
8. **명부 중복**: `fn_sector_map_as_of(trade_date)` 를 `stock_code` 로 묶어 `count(*) > 1` 이 **0 이 아니면 FAIL**(겹치는 유효기간 = `n_members` 이중 계산).
9. **summary 부재**: 오늘 `sector_summary_{trade_date}.json` 이 없으면 WARN · 3거래일 연속 FAIL. **이력 부족 vs 이력 유실**: 직전 `collection_reconciliation(dataset='sector')` 행은 있는데 그 날짜의 summary 파일이 없으면 「유실」로 WARN(부족은 PASS+사유).
판정 어휘 = **PASS / WARN / FAIL**(재무와 동일). FAIL 하나라도 있으면 FAIL · WARN 만 있으면 WARN.
결과는 `sector_writer` 자체 SQL 로 `collection_reconciliation(trade_date=ISO 'YYYY-MM-DD'(재무와 같은 형식 · minute 의 'YYYYMMDD' 와 섞지 않는다), dataset='sector', real_rows=성적표 행수, new_rows=corp_code 있고 ksic_code NULL 인 수(잔량 · §8-4), overlap=no_label, coverage=ksic_code 커버리지(비-NULL 비율), value_match_rate=ksic3_name **비-NULL 비율**(다른 데이터셋과 같이 «높을수록 좋다» — NULL 비율을 넣으면 교차 경보가 매일 울린다), verdict)` 에 쓴다 — 빈 열 셋을 이력 보조로 쓴다.

---

## 9. 테스트 (전부 red 먼저)

| # | 파일 | 무엇을 잡나 |
|---|---|---|
| T1 | `test_sector_writer.py` | 우선주 규칙: `00104K→001040`·`000087→000080` 복사 · `0001A0`(끝 '0')은 보통주 · **부모 없음 → NULL** · **부모 있으나 KSIC 없음(`0220WL`→`0220W0`) → NULL** (두 분기 다) · **부모 코드 값→값 변경 → 자식도 새 줄**(우선주는 부모 규칙이 열린 줄 값보다 우선) |
| T2 | 〃 | SCD2: 값 같음 → 새 줄 0 · **NULL→값 → 제자리 채움** · 값→다른 값 → `valid_to=trade_date−1`·새 줄 `valid_from=trade_date` · **열린 줄 `valid_from==trade_date` → 제자리** · **`valid_from>trade_date` → 건너뜀+카운트** · `collected_at` 불변·`last_seen_at`·`source_asof` 갱신 · **새 값 NULL 은 변경 아님** · **새 줄의 `ksic_checked_at` 은 닫힌 줄 값 승계**(NULL 로 떨어져 큐 맨 앞으로 튀지 않는다) |
| T3 | 〃 | 급변 가드: 값→값 5% 초과 → RuntimeError · 한 행도 안 씀(롤백) · NULL→값 300건은 가드 안 걸림 · 분모 0 이면 생략 |
| T4 | `test_sector_collector.py` | 캐시 규모 하한: KOSDAQ 묶음만 20건 → 한 행도 안 씀 · **기존 0건 면제 분기** · KONEX 무시 · 7일 후퇴 폴백과 `source_asof` 기록 · 8일째 404 → 실패 |
| T5 | 〃 | KSIC 절단: 길이 3·**길이 4** 코드는 `ksic5` 미정(4자리 키가 CHECK 를 통과하지 못함) · `ksic2`·`ksic3` 라벨 · 20일 창 밖 `prev_close` 미정 · 창 안 `close<=0` 행은 `prev_close` 후보에서 제외 |
| T6 | 〃 | 백분위 손계산 ①동률: G=4 중앙값 [3,1,1,−2] → rank **[0,2,2,3]** · pct **[100, 33.3, 33.3, 0]** ②동률 없음: [3,1,0,−2] → [0,1,2,3] · [100, 66.7, 33.3, 0] ③G=1 → NULL |
| T7 | 〃 | 같은 날 두 번 실행 → 행수·값 무변경(UPSERT) |
| T8 | 〃 | DART 020 → 채우기 중단, 성적표 진행 · 키 없음 → 채우기 스킵 · nodata 30일 미경과 호출 0 |
| T9 | `test_sector_stats_oracle_db.py` | 🔴 **오라클**(실 DB · 2026-08-05): 태쏘 `load_day`+`labels_for(N=3)` 의 종목별 `r`·라벨 vs 우리 계산. **import 방식**: `sys.path.insert(0, <repo>/backtest/tasso_program_journal)` 뒤 `pytest.importorskip('run_sector')`(패키지 아님 · 형제 모듈 5개와 `run_tests.DSN` 하드코딩을 끌어온다 — 그 DSN 은 `kis_template`@5433 SELECT 전용이라 죽은 DB 가 아니다) · DB 없거나 트리 없으면 **skip** · `@pytest.mark.db` 로 표시하고 **기준선 실패 집합 비교에서 제외**(워크트리 환경 차이). **허용 차집합 딱 둘** — ①`market_cap` NULL/≤0(태쏘만 제외 · 이 날짜엔 0건 예상, 인쇄 · **2024-03-12 이전은 이 테스트가 재지 않는다** §3.2) ②**`ksic_source IS DISTINCT FROM 'snapshot_20260807'`**(부모복사·DART 채움 — 우리만 라벨 있음). 그 밖의 차이 1건이라도 있으면 실패. 교집합 종목의 `r`·`ksic3` 완전 일치 · ② 종목이 없는 업종의 `ret_median`·`n_members` 일치 · `G` 차이 = ② 로만 생긴 업종 수 |
| T10 | `test_eod_collection.py` | `"sector"`·`"sector_reconcile"` 키 · 순서 = `financials_reconcile` 뒤 · **`_stub_flow_stages` 에 두 함수 추가** · 예외 격리 |
| T11 | `test_sector_writer_db.py` | DDL 멱등 · CHECK 제약 발동 · **`SELECT * FROM fn_sector_map_as_of(d)` 왕복** · 경계(valid_from 당일 포함 · valid_to 당일 포함 · 다음날 제외) · **표본 날짜 10개에서 종목당 ≤ 1행** |
| T12 | 〃 | 이름표: `ksic_code` NULL/길이<3 행 제외 · 최빈 · 점유율 < 0.8 WARNING · 우선주(부모복사) 포함 집계 |
| T13 | `test_sector_reconcile.py` | summary json 저장·읽기 · 이력 부족 → PASS+사유 · 이력 유실 → WARN · 오늘 summary 없음 1일 WARN·3일 FAIL · §8-3 `no_prev` 문턱(기저 0 에서 1건은 WARN 아님 · 189 는 WARN) · §8-4 `0=0=0` 은 WARN 아님 · `recheck_calls` 20일 0 → WARN · §8-5 `written=false` 2일 → FAIL · `last_seen_at` 3거래일 정체 → FAIL · §8-6 NULL 비율 급증 → WARN · §8-7 게시 지연 3일 → WARN · §8-8 중복 → FAIL · §8-1 분자가 U_market 한정 · trade_date ISO · verdict 어휘 |
| T14 | `test_sector_collector.py` | 실패 경로: ①에서 RuntimeError → ②③④ 진행 · summary `written=false` 로 **항상** 저장 · §5-5 시간 가드(평일 16:00 에 `--backfill` 거부 · `--force` 허용) · `--dry-run` 쓰기 0 · 재확인 순환: 예산 = 300 − 채우기 · `ASC NULLS FIRST` 순서 · 값→값 응답이 새 줄을 연다(`ksic_checked_at=now()`) · 우선주 행은 DART 대상 아님 · **레일: 값→값 31건 → 전부 롤백 + RuntimeError** · (c) 우선주 재복사가 (b) 뒤에 돈다 · `dart_company_*.jsonl` 보관 |

기존 전체 스위트 실패 집합은 main 과 **양방향 차분 0**(회귀 판정 규칙).

---

## 10. 라이브 영향과 경계

| | |
|---|---|
| 매매 동작 변경 | **0줄** |
| `eod_collection.py` | **+2줄**(`financials_reconcile` 뒤) |
| 기존 테이블 | **무변경** — `stock_industry`·`stock_sector`·`sector_index_daily`·`dart_corp_code`(행은 늘지만 스키마·의미 불변) |
| KIS API | **0호출** |
| DART | corpCode.xml 주 1회 + company.json ≤ 300/일 |
| 외부 의존 신규 | **GitHub `fdr_krx_data_cache`** 직접 읽기(KRX 포털 호출 0 · 404 는 §7 · 게시 지연은 §8-7) |
| 보관 파일 | `scratchpad/sector/` 의 `krx_desc_*.csv.gz`(≈300KB/일 · 연 75MB) + `sector_summary_*.json`(수 KB/일) — **삭제 금지 · 회전 없음**(§5-4 재생성의 원료) |
| 롤백 | EOD 2줄 제거. 표·함수는 남겨도 무해(읽는 코드 없음) · 성적표 데이터 롤백은 §6.2 |

**범위 밖**
- 🔴 뉴스·공시의 섹터 집계·API·시그널(**스펙 B**) — A 완료 후 같은 절차.
- 🔴 라이브 매수 후보 표시(10월 말) — 별도 결정.
- 🔴 문서 3 의 절단 자릿수 동결·`Ps` 정의·LOO 재계산 — 문서 3 사전등록 몫(§3.6 ①).
- 🔴 테마·대장주 분류(2026-08-07 확정 불가) · `sector_index_daily` 되살리기 · KRX 79업종 갱신 소스.
- 🔴 종목별 LOO 성적표(≈ 1,100만 행) — 안 만든다.
- ⚠️ 부트스트랩 소급 편향 크기 — 재지 않는다(§5-2).

---

## 11. 완료 판정

1. T1~T14 통과 + 전체 스위트 실패 집합 main 과 동일.
2. 부트스트랩 리포트(§6.0-5): U_market 대비 `ksic_code`·`ksic3_name` 각 ≥ 98%(3 단계 «후» 측정) · **미라벨 종목 목록** · DART 125 응답 실측 · 이름표 코드 수(기대 ≥ 155) · 점유율 < 0.8 목록(기대 0건).
3. 백필 리포트(§6.2): 2021-01-04 ~ 어제 · 성적표 날짜 수 = `daily_prices` 고유 날짜 수 − 1(첫날 제외 · 1,391 기준) · 일자별 G 분포 · 라이브 3표 전후 동일 · **소급 문장 + 「2024-03-12 이전은 태쏘와 미대조」 문장**.
4. 오라클(T9) 실 DB 통과 기록(교집합·허용 차집합 ①②의 수 인쇄).
5. 머지 후 다음 거래일 EOD 에서 `collection_reconciliation(dataset='sector')` **PASS** 관측 — 단 첫날 허용되는 WARN 은 셋뿐: §8-7(주말 `source_asof`) · §8-3(신규상장 소수) · «이력 부족». 그 밖의 WARN/FAIL 은 미완료.
6. 문서: 이 스펙 §6.0·§6.2 실측 갱신 · `docs/DB통합_쉬운설명.md` 표 목록에 신규 표 추가 · 쉬운 한 장 `docs/섹터데이터_쉬운설명_<작성일>.md` · changelog.

(메모리 참조 — 레포 밖 파일) `changelog-2026-09-06-financial-data-quality-audit` · `reference-ksic-industry-not-usable-for-theme` · `reference-newsquant-db-access` · `reference-pykrx-marketcap-endpoint-dead`
