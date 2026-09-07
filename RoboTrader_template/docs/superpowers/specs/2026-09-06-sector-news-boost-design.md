# 섹터 뉴스 부스트 (스펙 B) — 뉴스 키워드·종목매핑 → KSIC3 섹터 점수 → 매수후보 재정렬 — 설계 v1.2 (2026-09-06 · 정정 2026-09-07)

> **이력** — v1(2026-09-06, 사장님 승인) → **v1.1**(2026-09-07, 구현 계획 작성 중 발견한 정정 7건 — §13. 결정 10개는 불변). 구현 계획: 봇 측 `docs/superpowers/plans/2026-09-07-sector-news-boost-bot.md` · NewsQuant 측 `D:\GIT\NewsQuant\docs\superpowers\plans\2026-09-07-sector-news-boost-newsquant.md`.

> 사장님 결정(2026-09-06 밤, 브레인스토밍 5문답): 섹터 기준 = **KSIC 3자리(스펙 A 위)** · 뉴스→섹터 = **키워드 사전 + 종목매핑 둘 다** · 적용 시점 = **09:00 후보 로드 시 재정렬** · 방향 = **양방향(긍정 가산·부정 감산)** · 롤아웃 = **shadow 먼저, 플래그로 live** · 계산 주체 = **NewsQuant → 공유 DB 테이블, 봇은 읽기만(1안)**.
> 이 문서는 스펙 A(`2026-09-06-sector-data-design.md`) §3.6 소비자 계약 ②「NewsQuant 는 `news.related_stocks` → `fn_sector_map_as_of(공시일)` → `ksic3` → 조인(스펙 B)」를 구체화한 **스펙 B** 다. 두 리포(`D:\GIT\NewsQuant`, `D:\GIT\kis-trading-template`)에 각각 변경이 들어간다.

---

## 0. 사실 (2026-09-06 실측)

두 리포 탐색과 DB 직접 조회로 확인한 것만 적는다.

- **DB 는 이미 공유 중.** NewsQuant 는 2026-08-16 부터 `kis_template`(localhost:5433)에 직접 쓴다(`config.yaml`). `public` 스키마 67표 **전부 `robotrader` 소유**(`news`·`collection_log` 포함). NewsQuant 접속 롤은 `postgres`(superuser).
- **스펙 A 상태.** 브랜치 `feat/sector-data`(워크트리 `D:/tmp/kis-wt-sector`)에서 구현 중. DDL(`stock_sector_map`·`sector_daily_stats`·`ksic_code_name`·`sector_ksic_nodata`·`fn_sector_map_as_of`)은 DB 에 **이미 적용**됐으나 **전부 0행**(부트스트랩·백필 미실행). main 에는 아직 코드가 없다.
- **뉴스.** `news` 203,892행. `related_stocks`(쉼표 연결 6자리 코드) 채움률 53.6%. 글로벌 소스(cnbc·marketwatch·investing_com·google_news_*)는 **0%**(`global_news_crawler.py:231` 하드코딩 `''`). DART 공시가 행의 74%. 9/3 이후 이틀치: dart 1,101 · naver 967 · hankyung 279 · investing 206 · mk 123 · google 252 · cnbc 88 · marketwatch 30.
- **`related_stocks` 노이즈.** 「[인사] 국토교통부」→ 005930 외 3종목, 「퇴직연금 적립금 500조」→ 012030, 「국민연금에 맡기면…」→ 035420. 이름 부분문자열 매칭(`base_crawler.extract_stock_codes`)의 한계다.
- **키워드 추출 모듈은 없다.** NewsQuant 의 「키워드」는 감성 사전(하드코딩 리스트, `sentiment_analyzer.py:24-150`)이며 기사별 키워드는 저장되지 않는다. 뉴스 1건당 저장되는 것은 `sentiment_score`(−1..1)·`importance_score`·`impact_score`·`timeliness_score`·`overall_score`·`duplicate_count`.
- **NewsQuant 프로세스 생존.** 마지막 행 `2026-09-04 20:36`(금). 주말 30분 주기 수집이 있어야 하는데 없다 → 야간·주말에 프로세스가 죽어 있다. Task Scheduler `\RoboTrader_AutoStart` 07:40 → `D:\GIT\run_all_robotraders.bat` [4/5] `NewsQuant\start.bat`, [5/5] 봇.
- **봇의 후보 경로.** `main._main_trading_loop` 는 `is_market_open()` 이 참이 되는 **09:00 첫 루프**에서 `_load_screener_candidates` 를 1회 호출한다(07:40 기동 직후가 아니다). 경로: `run_screener_snapshot_hook`(D-1 스냅샷, 없을 때만 생성) → `select_candidates_per_strategy` → `_fetch_candidates_for_strategy`(`screener_snapshots` 에서 rank 순 코드, `score=50.0` 자리표시, `name=code`) → `_filter_unsafe_stocks(pool, limit=MAX_CANDIDATES_PER_STRATEGY=20)` → `add_selected_stock`. **봇은 `news` 를 한 줄도 읽지 않는다**(감사 2026-08-23 확인, 이번 grep 재확인).
- **전략 점수는 로드 시점에 없다.** `screener_snapshots.score` 는 전략마다 단위가 다르고(120일 수익률 · 평균 거래량 · 0~100 점), 로드 경로는 코드 순서만 쓴다. ⇒ 재정렬은 **순위 이동**으로만 가능하다.
- **전문가 자문(2026-09-06).** 섹터·재무는 「컷」이 아니라 「순위」. shadow 기록 후 활성화 판단. 「섹터」는 부호가 반대인 두 축(오닐식 선도업종 vs 눌림목 동조)이라 전략별로 갈라 봐야 한다.

---

## 1. 결정 사항 (🔒 = 사장님 결정)

1. 🔒 섹터 분류 = **KSIC 3자리**(`fn_sector_map_as_of` 의 `ksic_code` 앞 3자리). KRX 79업종(`stock_sector`)은 쓰지 않는다.
2. 🔒 뉴스→섹터 귀속은 **경로 A(키워드 사전, 제목·본문)** 와 **경로 B(`related_stocks` → `fn_sector_map_as_of(D-1)` → KSIC3)** 둘 다. 같은 뉴스가 여러 섹터에 귀속될 수 있다.
3. 🔒 적용 시점 = **09:00 후보 로드**, `_fetch_candidates_for_strategy` 안에서 안전필터 **앞**. 스냅샷 표는 손대지 않는다.
4. 🔒 방향 = **양방향**. 섹터 점수 `score_signed ∈ [−1, +1]`.
5. 🔒 롤아웃 = **shadow 기본값**. `SECTOR_NEWS_BOOST_MODE ∈ {off, shadow, live}`, live 전환은 §8 평가 뒤 사장님 결정. env 한 줄로 켜고 끈다.
6. 🔒 계산 주체 = **NewsQuant**. 결과는 공유 DB 표 `sector_news_score` 로 넘긴다. 봇은 읽기 + 자기 기록 표 쓰기만. HTTP 의존 0.
7. 재정렬은 **순위 이동**이며 상한 `SECTOR_NEWS_MAX_SHIFT=3` 칸. 전략 점수 스케일이 제각각이고 로드 시점에 점수가 없기 때문(§0).
8. 봇 쪽은 **fail-open**: 이 기능의 어떤 실패도 후보 조회·매수를 막지 않는다(원래 순서 유지 + WARNING). 기존 `_fetch_candidates_for_strategy` 의 fail-closed 는 「후보 조회 자체」의 규칙이고, 재정렬은 장식이다.
9. 매매 룰 0줄 · 라이브 3표(`daily_prices`·`minute_candles`·`virtual_trading_records`) 불변 · KIS 호출 0 · 스펙 A 표 4개는 **읽기만**.
10. 스펙 A 가 배포되기 전에도 NewsQuant 측은 먼저 올릴 수 있다(경로 A 는 A 에 의존하지 않는다). 봇 측은 `fn_sector_map_as_of` 가 없거나 비어 있으면 매일 WARNING + 기록만 남긴다.

---

## 2. 구성요소

### 2.1 NewsQuant (`D:\GIT\NewsQuant`)

| 파일 | 역할 | 신규/수정 |
|---|---|---|
| `news_scraper/data/sector_keywords.yaml` | KSIC3 별 한/영 키워드 사전(§4.2). `version` 필드가 `dict_version` 으로 기록된다 | 신규 |
| `news_scraper/sector_news_aggregator.py` | 순수 로직: 사전 로드·검증, 창 계산, 뉴스 1건 → 섹터 귀속(경로 A·B), 기여도·집계, 결과 dict 생성. **DB 를 모른다**(입력은 뉴스 dict 리스트 + 코드→KSIC3 dict) | 신규 |
| `news_scraper/database.py` | DDL 2표(§3.1·3.2, `init_database` 에 추가) · `upsert_sector_news_scores()` · `replace_news_sector_hits()` · `get_sector_map_as_of(as_of, codes)` · `get_news_in_window(start, end)` · `get_sector_news_scores(trade_date)` (**DB 쓰기는 이 파일뿐**, 기존 관례 유지) | 수정 |
| `news_scraper/scheduler.py` | `IntervalTrigger(minutes=10)` 잡 `sector_news_aggregation` 등록. 기동 시 첫 수집 직후 1회 즉시 실행 | 수정 (⚠️ 현재 워킹트리에 미커밋 diff 254줄이 있다 — 그 위에서 작업하거나 먼저 정리한다) |
| `news_scraper/api/server.py` | `GET /api/sector/news-score?trade_date=YYYY-MM-DD` (점검용, 기본 = 오늘) | 수정 |
| `requirements.txt` | `pyyaml`(이미 `config.py` 가 import 하는데 누락) · `pytest`(dev) 추가 | 수정 |
| `pyproject.toml` (신규, 루트) | `[tool.pytest.ini_options] testpaths=["tests"] markers=["db: ..."]` | 신규 |
| `tests/` | §7 (디렉터리 신설) | 신규 |
| `docs/섹터뉴스부스트_스펙B_포인터_2026-09-06.md` | 이 문서로의 포인터(사본 아님) | 신규 |

### 2.2 kis-trading-template (`RoboTrader_template/`)

| 파일 | 역할 | 신규/수정 |
|---|---|---|
| `core/sector_news_rerank.py` | 순수 함수 `rerank(...)`(§5.2) + 결과 dataclass. DB·로거 의존 없음 | 신규 |
| `db/repositories/sector_news.py` | `SectorNewsRepository(BaseRepository)`: `get_scores(trade_date)` · `get_sector_map(as_of, codes)` · `save_rerank_log(rows)` · `ensure_table()` | 신규 |
| `db/migrations/20260907_sector_news_rerank_log.sql` | §3.3 DDL 기록용(SSOT 는 `ensure_table`) | 신규 |
| `db/database_manager.py` | `self.sector_news_repo = SectorNewsRepository()` 1줄 | 수정 |
| `config/constants.py` | §5.3 상수 5개 | 수정 |
| `core/candidate_selector.py` | `_fetch_candidates_for_strategy` 에 `codes = self._apply_sector_news_rerank(strategy_name, codes, prev_day_str)` 1줄 + 헬퍼 메서드(모드 분기·fail-open·기록·로그) | 수정 |
| `bot/candidate_loader.py` | live 모드일 때 텔레그램 후보 알림에 이동 표기(선택, §5.6) | 수정(소) |
| `tests/core/test_sector_news_rerank.py` · `tests/test_candidate_sector_news_wiring.py` · `tests/db/test_sector_news_repo_db.py` | §7 | 신규 |
| `scripts/eval_sector_news_shadow.py` | §8 평가(연구 트리) | 신규 |
| `docs/DB통합_쉬운설명.md` | §9 표 목록에 3표 추가 | 수정 |

**경계**: `sector_news_aggregator`(NQ)와 `sector_news_rerank`(봇)는 둘 다 순수 함수 모듈이며 DB 를 모른다. 두 리포 사이 계약은 **표 두 개**(`fn_sector_map_as_of` 읽기 · `sector_news_score` 읽기)뿐이다.

---

## 3. 스키마

### 3.1 `sector_news_score` — 거래일 × 섹터 점수 (NewsQuant 쓰기 · 봇 읽기)

```sql
CREATE TABLE IF NOT EXISTS sector_news_score (
    trade_date    date        NOT NULL,   -- 이 점수가 쓰일 거래일 (§4.1)
    taxonomy      text        NOT NULL DEFAULT 'ksic3',
    sector_key    text        NOT NULL,   -- '261'
    sector_name   text,                   -- 사전 name → fn_sector_map_as_of.ksic3_name → NULL 순
    window_start  timestamp   NOT NULL,
    window_end    timestamp   NOT NULL,
    n_news        integer     NOT NULL,   -- 창 안 귀속 뉴스 수(뉴스×섹터 중복 제거)
    n_dir         integer     NOT NULL,   -- 그중 |sentiment| >= 0.1 인 「방향 있는」 뉴스 수
    n_kw          integer     NOT NULL,   -- 경로 A 로 귀속된 수
    n_stock       integer     NOT NULL,   -- 경로 B 로 귀속된 수 (A·B 둘 다면 양쪽 셈)
    n_pos         integer     NOT NULL,   -- sentiment >= +0.1
    n_neg         integer     NOT NULL,   -- sentiment <= -0.1
    score_raw     double precision NOT NULL,  -- Σ c_i
    score_norm    double precision NOT NULL,  -- score_raw / sqrt(max(n_dir,1))
    score_signed  double precision NOT NULL,  -- clip(score_norm / K_SCALE, -1, +1); n_dir < MIN_N 이면 0
    top_news      jsonb,                  -- |c| 상위 5건 [{news_id, title, c, route}]
    dict_version  text,
    computed_at   timestamp   NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, taxonomy, sector_key)
);
CREATE INDEX IF NOT EXISTS idx_sns_date ON sector_news_score (trade_date, computed_at DESC);
```

- 한 거래일에 여러 번 UPSERT 된다(10분 주기). 봇은 `trade_date = 오늘` 행을 읽고 `computed_at` 으로 신선도를 판정한다(§5.5).
- `n_dir < MIN_N` 인 섹터도 **행은 쓴다**(`score_signed = 0`). 「뉴스가 없었다」와 「계산이 안 돌았다」를 가르기 위해서다.
- 창 안에 귀속 뉴스가 하나도 없는 섹터는 행을 쓰지 않는다. 그날 행이 하나도 없으면 봇은 `no_score_rows` 로 처리한다.

### 3.2 `news_sector_hit` — 뉴스 × 섹터 귀속 기록 (사전 튜닝·사후 검증용)

```sql
CREATE TABLE IF NOT EXISTS news_sector_hit (
    trade_date    date    NOT NULL,
    news_id       text    NOT NULL,       -- news.news_id
    sector_key    text    NOT NULL,
    route         text    NOT NULL,       -- 'kw_title' | 'kw_body' | 'stock' (가중치 최대인 경로)
    routes        text    NOT NULL,       -- 걸린 경로 전부, 쉼표 (예: 'kw_title,stock')
    matched       text,                   -- 걸린 키워드 / 종목코드 (디버그용, 200자 절단)
    w_match       double precision NOT NULL,
    contribution  double precision NOT NULL,   -- c_i
    computed_at   timestamp NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, news_id, sector_key)
);
```

- 같은 `trade_date` 재계산 때는 그 날짜 행을 **지우고 다시 쓴다**(창이 넓어지며 귀속이 바뀔 수 있다). 한 트랜잭션.
- 기존 orphan 표 `news_stock`(트리거 파생, 498k행)과 무관하다. 건드리지 않는다.

### 3.3 `sector_news_rerank_log` — 봇의 재정렬 기록 (봇 쓰기)

```sql
CREATE TABLE IF NOT EXISTS sector_news_rerank_log (
    trade_date    date    NOT NULL,
    strategy      text    NOT NULL,
    stock_code    varchar(20) NOT NULL,
    sector_key    text,                   -- NULL = 섹터 미상
    sector_score  double precision,       -- score_signed (미상이면 NULL)
    orig_rank     integer NOT NULL,       -- 스냅샷 순위(1-based)
    new_rank      integer NOT NULL,       -- 재정렬 후 순위 (shadow 에서도 「됐을」 순위)
    applied       boolean NOT NULL,       -- live 에서 실제 적용됐으면 true
    mode          text    NOT NULL,       -- 'shadow' | 'live'
    reason        text    NOT NULL,       -- 'ok' | 'no_score_rows' | 'stale' | 'fn_missing' | 'table_missing' | 'excluded_strategy' | 'error:<종류>'
    score_asof    timestamp,              -- 읽은 sector_news_score.computed_at (max)
    created_at    timestamp NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, strategy, stock_code)
);
```

- `reason != 'ok'` 이면 `new_rank = orig_rank`, `sector_score = NULL` 로 **그래도 행을 쓴다**. §8-③ 「이동 0 인 날의 원인」이 여기서 나온다.
- 같은 날 재로드(`reload_candidates`)가 있으면 UPSERT 로 덮는다.

### 3.4 소유·권한

- NewsQuant 는 `postgres` 로 접속하므로 `CREATE TABLE` 결과가 `postgres` 소유가 된다. DB 관례(67표 전부 `robotrader`)를 지키고 봇이 읽게 하려고 DDL 직후 `ALTER TABLE ... OWNER TO robotrader` 를 실행한다(멱등). 권한 없는 롤로 돌 때를 대비해 try/except + WARNING(치명 아님).
- `sector_news_rerank_log` 는 봇(`robotrader`)이 만든다.

---

## 4. NewsQuant 측 — 데이터 흐름

```
[10분마다]
now → trade_date, window = [직전 거래일 15:30, now]           (§4.1)
news(window, published_at 인덱스) ─┬─ 경로 A: 사전 매칭(제목 1.0 / 본문 0.5)      ─┐
                                   └─ 경로 B: related_stocks → get_sector_map_as_of(D-1) → KSIC3 (0.7) ─┼─ 뉴스×섹터 c_i
섹터별 집계(§4.4) ──► sector_news_score UPSERT ──► news_sector_hit REPLACE(그 trade_date)
```

### 4.1 창과 `trade_date`

- `trade_date` = 평일이고 `now < 15:30` 이면 **오늘**, 아니면 **다음 평일**. 공휴일 달력은 NewsQuant 에 없으므로 무시한다(봇은 휴장일에 로드하지 않는다). ⚠️ **정정(v1.2, §14-2)**: 이 근사는 창을 «넓히는» 게 아니라 공휴일 뒤에는 창을 «좁힌다» — 월요일이 휴장이면 화요일 창의 시작이 월요일 15:30 이 되어 월요일 낮 뉴스가 통째로 빠진다. v1 구현은 이 정의대로이고, 보정은 §14-2 후속.
- `window_start` = **직전 평일 15:30**(월요일이면 금요일 15:30). `window_end` = now. D-1 장중 뉴스는 D-1 종가(=스크리너 스냅샷)에 이미 반영됐다고 보고 **뺀다**.
- 시간 감쇠는 v1 에 없다(§10).

### 4.2 키워드 사전 (경로 A)

**형식** — `news_scraper/data/sector_keywords.yaml`

```yaml
version: "2026-09-06.1"
sectors:
  "261":
    name: 반도체 제조업
    ko: [반도체, 메모리반도체, D램, 낸드, HBM, 파운드리, 웨이퍼]
    en: [semiconductor, chip, chips, DRAM, NAND, HBM, foundry, wafer]
    exclude: [반도체 ETF]          # 선택. 걸리면 이 섹터 귀속 취소
```

**검증 규칙**(로드 시 실패 = 잡 중단 + ERROR, 기동은 계속): 키는 3자리 숫자 문자열 · `name` 필수 · `ko`/`en` 중 하나 이상 비어 있지 않음 · 중복 키워드 금지. `ksic_code_name` 이 채워진 뒤에는 **키가 그 표에 없으면 WARNING**(중단 아님).

**매칭 규칙**
- 한국어: 소문자화 후 **부분문자열**(기존 감성 사전과 같은 방식. 한국어엔 `\b` 가 없다).
- 영어: 소문자화 후 **단어경계** `(?<![a-z0-9])kw(?![a-z0-9])`. `chip` 이 `chipotle` 에 걸리지 않는다.
- 제목에 걸리면 `kw_title`(1.0), 본문에만 걸리면 `kw_body`(0.5). 본문은 앞 **2,000자**만 본다.
- `exclude` 가 제목·본문 어디든 걸리면 그 섹터 귀속을 취소한다.
- 한 뉴스가 여러 섹터에 걸리면 **전부** 귀속한다(바이오 뉴스가 211·212·701 에 동시에 가는 것이 맞다).

**초기 대상 — 뉴스에 자주 등장하는 49개 섹터**(코드는 `ksic_code_name` 으로 최종 확인; 이름은 2026-09-04 캐시 CSV `Industry` 열)

| 묶음 | KSIC3 · 이름 |
|---|---|
| 전자·반도체 | 261 반도체 · 262 전자부품 · 263 컴퓨터 및 주변장치 · 264 통신 및 방송 장비 · 265 영상 및 음향기기 · 292 특수 목적용 기계(반도체·디스플레이 장비) · 291 일반 목적용 기계 |
| 바이오·의료 | 211 기초 의약물질 · 212 의약품 · 213 의료용품 및 기타 의약 관련제품 · 271 의료용 기기 · 701 자연과학 및 공학 연구개발업(바이오벤처) |
| 자동차·운송장비 | 301 자동차용 엔진 및 자동차 · 303 자동차 신품 부품 · 311 선박 및 보트 · 313 항공기·우주선 및 부품 · 252 무기 및 총포탄(방산) |
| 소재·에너지 | 241 1차 철강 · 242 1차 비철금속 · 282 일차전지 및 이차전지 · 281 전동기·발전기·전기 변환장치(전력기기) · 283 절연선 및 케이블 · 201 기초 화학물질 · 204 기타 화학제품(화장품 포함) · 192 석유 정제품 · 351 전기업 · 352 연료용 가스 |
| IT·미디어·통신 | 582 소프트웨어 개발 및 공급(게임 포함) · 620 컴퓨터 프로그래밍·SI · 631 자료처리·호스팅·포털 · 612 전기 통신 · 602 텔레비전 방송 · 591 영화·방송프로그램 제작 · 592 오디오물 출판(음악) · 713 광고 |
| 금융 | 641 은행 및 저축기관 · 651 보험 · 649 기타 금융 · 661 금융 지원 서비스(증권) · 664 신탁·집합투자 |
| 건설·부동산 | 411 건물 건설 · 412 토목 건설 · 681 부동산 임대 및 공급 |
| 소비·유통·운송 | 107 기타 식품 · 111 알코올음료 · 471 종합 소매 · 501 해상 운송 · 511 항공 여객 운송 · 752 여행사 |

나머지 109개 섹터(158 − 49)는 경로 B 로만 잡힌다. 사전은 §8 평가 뒤 `news_sector_hit` 를 보고 늘린다.

### 4.3 경로 B — 종목매핑

- `news.related_stocks` 를 쉼표로 나눠 6자리 코드 집합을 만든다. 창 안 뉴스의 코드 합집합으로 **한 번** `get_sector_map_as_of(D-1, codes)` 를 부른다(`SELECT stock_code, left(ksic_code,3) AS ksic3, ksic3_name FROM fn_sector_map_as_of(%s) WHERE stock_code = ANY(%s) AND ksic_code IS NOT NULL AND length(ksic_code) >= 3`).
- D-1 = 직전 평일(§4.1). 스펙 A 규칙대로 `length(ksic_code) < 3` 은 미정.
- `fn_sector_map_as_of` 가 **없거나**(스펙 A 미배포) 호출이 실패하면 경로 B 를 **끄고** WARNING 1줄 + `n_stock=0` 으로 계속한다. 경로 A 는 영향 없다.
- 가중 0.7 (§0 노이즈). 한 뉴스에 코드가 **5개 초과**면 인사·시황 나열 기사로 보고 경로 B 를 **건너뛴다**(건수를 summary + WARNING 에 남긴다 — 무징후 절단 금지).

### 4.4 기여도·집계

뉴스 i, 섹터 s:

```
w_match(i,s) = max( kw_title 1.0, kw_body 0.5, stock 0.7 )   -- 걸린 경로 중 최대값 하나만
w_src(i)     = SOURCE_CREDIBILITY.get(source, 0.9)            -- sentiment_analyzer.py:150 재사용
c(i,s)       = sentiment_score(i) × w_match(i,s) × w_src(i)

n_news(s) = |{i : 귀속}|
n_dir(s)  = |{i : 귀속 ∧ |sentiment_score(i)| >= 0.1}|      -- 중립(DART 정형 공시 대부분)은 분모에 넣지 않는다
score_raw(s)    = Σ_i c(i,s)
score_norm(s)   = score_raw(s) / sqrt(max(n_dir(s), 1))      -- 방향 일관성 × 규모, n 에 비례하지 않게
score_signed(s) = 0                                if n_dir(s) < MIN_N      (MIN_N = 3)
                = clip(score_norm(s) / K_SCALE, -1, +1)  otherwise           (K_SCALE = 2.0)
```

- 상수 `MIN_N`·`K_SCALE`·`W_KW_BODY`·`W_STOCK`·`MAX_CODES_PER_NEWS`·`BODY_CHARS` 는 `sector_news_aggregator.py` 상단 모듈 상수. `config.yaml` 로 빼지 않는다(현재 `config.yaml` 은 어떤 점수 상수도 갖지 않는다 — 관례 유지).
- 중립 뉴스를 분모에서 빼는 이유: DART 정형 공시(「임원ㆍ주요주주특정증권등소유상황보고서」 등)가 행의 74% 이고 거의 전부 0점이다. 넣으면 큰 섹터일수록 점수가 체계적으로 눌린다.
- 확산도(`duplicate_count`)·중요도(`importance_score`)는 v1 에서 쓰지 않는다(§10, 노브 하나씩 추가).

### 4.5 스케줄·실패 처리

- `scheduler.py`: `add_job(self.run_sector_news_aggregation, IntervalTrigger(minutes=10), id='sector_news_aggregation', max_instances=1, misfire_grace_time=300)`. `start()` 에서 첫 `collect_all_news()` 직후 1회 즉시 호출.
- 한 실행의 순서: 창·trade_date 계산 → 뉴스 조회 → 사전 로드(실패 시 ERROR 후 return) → 경로 B 맵 조회(실패 시 경로 B 비활성) → 집계 → **한 트랜잭션**으로 `news_sector_hit` DELETE+INSERT · `sector_news_score` UPSERT → INFO 1줄(`[섹터뉴스] trade_date=… 창=… 뉴스 N · 귀속 M · 섹터 K · 경로B {on|off} · 절단 J · {ms}`).
- 예외는 잡 안에서 잡아 ERROR 로 남기고 스케줄러를 죽이지 않는다(기존 `_handle_crawler_result` 관례).
- 예상 비용: 창 안 뉴스 2~4천 건 × 사전 ~400 키워드 → 수백 ms. DB 쓰기 수백 행.

### 4.6 API (점검용)

`GET /api/sector/news-score?trade_date=YYYY-MM-DD`(기본 = §4.1 의 오늘 `trade_date`) → `{success, trade_date, count, computed_at_max, data:[행…]}`. `score_signed` 내림차순. 봇은 **이 엔드포인트를 쓰지 않는다**(결정 6).

---

## 5. 봇 측 — 재정렬

### 5.1 삽입 지점

`core/candidate_selector._fetch_candidates_for_strategy`:

```python
codes = provider(strategy_name, prev_day_str)          # 기존
...
if not codes: ... return []                             # 기존
codes = self._apply_sector_news_rerank(strategy_name, codes, prev_day_str)   # 🆕 1줄
pool = [CandidateStock(...) for code in codes]          # 기존
candidates = self._filter_unsafe_stocks(pool, limit=max_candidates)          # 기존
```

안전필터가 앞에서 `limit` 개를 자르므로 재정렬은 **그 앞**이어야 21위 종목이 20위 안에 들어올 수 있다. 스냅샷 표는 그대로다.

### 5.2 순수 함수 — `core/sector_news_rerank.py`

```python
@dataclass(frozen=True)
class RerankRow:
    stock_code: str; sector_key: Optional[str]; sector_score: Optional[float]
    orig_rank: int; new_rank: int

def rerank(codes: List[str],
           code_to_sector: Dict[str, str],           # code → '261'
           sector_scores: Dict[str, float],          # '261' → score_signed
           *, max_shift: int = 3, min_abs: float = 0.2) -> Tuple[List[str], List[RerankRow]]:
    """key_i = orig_rank_i − max_shift × s_i ; s_i = 0 if 섹터 미상 or |s_i| < min_abs.
    key 오름차순 «안정» 정렬 → 동률은 원래 순위 유지. 아무리 강해도 최대 max_shift 칸."""
```

- 입력 검증: `codes` 중복 금지(중복이면 ValueError — 스냅샷 계약 위반), `max_shift >= 0`.
- 예: 4위 종목 s=+1.0, K=3 → key 1 → 1위와 동률 → 원래 1위가 앞, 이 종목 2위.

### 5.3 상수 — `config/constants.py` (`SCREENER_SNAPSHOT_ENABLED` 와 같은 env 패턴)

| 상수 | 기본값 | env | 뜻 |
|---|---|---|---|
| `SECTOR_NEWS_BOOST_MODE` | `"shadow"` | `SECTOR_NEWS_BOOST_MODE` | `off` 조회 안 함 · `shadow` 계산·기록만, 원래 순서 반환 · `live` 새 순서 반환. 그 외 값은 WARNING 후 `off` |
| `SECTOR_NEWS_MAX_SHIFT` | `3` | — | 최대 이동 칸 |
| `SECTOR_NEWS_MIN_ABS` | `0.2` | — | 이보다 약한 `score_signed` 는 0 취급 |
| `SECTOR_NEWS_STALE_MINUTES` | `60` | — | `computed_at` 이 이보다 오래되면 없는 것으로 |
| `SECTOR_NEWS_EXCLUDE_STRATEGIES` | `frozenset()` | — | 적용 제외 전략(평균회귀 `deep_mr_dev20` 은 §8 결과 보고 결정) |

### 5.4 리포지토리 — `db/repositories/sector_news.py`

```python
class SectorNewsRepository(BaseRepository):
    def ensure_table(self) -> None                       # §3.3 CREATE IF NOT EXISTS (기동 시 1회)
    def get_scores(self, trade_date) -> Tuple[Dict[str, float], Optional[datetime]]
        # SELECT sector_key, score_signed, computed_at FROM sector_news_score WHERE trade_date=%s AND taxonomy='ksic3'
        # → ({sector: score_signed}, max(computed_at)). 행 0 이면 ({}, None)
    def get_sector_map(self, as_of, codes) -> Dict[str, str]
        # SELECT stock_code, left(ksic_code,3) FROM fn_sector_map_as_of(%s) WHERE stock_code = ANY(%s) AND length(ksic_code) >= 3
        # 함수 부재는 psycopg2.errors.UndefinedFunction → 그대로 올린다(호출자가 'fn_missing' 으로 분류)
    def save_rerank_log(self, rows: List[dict]) -> int   # UPSERT, 저장 건수
```

읽기·쓰기 모두 `BaseRepository._get_connection()`(라이브 풀, `TIMESCALE_*`, 5433). 연구 트리 import 0.

### 5.5 `_apply_sector_news_rerank` — 모드 분기와 fail-open

```
mode == off                     → codes 그대로, DB 접근 0, 로그 0
strategy in EXCLUDE             → 기록(reason='excluded_strategy', 이동 없음) → codes 그대로
scores, asof = get_scores(오늘)
  행 0                          → reason='no_score_rows'
  now − asof > STALE_MINUTES    → reason='stale'
code_to_sector = get_sector_map(D-1, codes)
  UndefinedFunction             → reason='fn_missing'
  UndefinedTable(sector_news_score) → reason='table_missing'
  그 밖의 예외                   → reason='error:<ExceptionName>'
reason != 'ok'                  → 기록(전 종목 new_rank=orig_rank) + WARNING 1줄 → codes 그대로
reason == 'ok'                  → new_codes, rows = rerank(...) ; 기록 ; INFO 1줄
                                  shadow → return codes ; live → return new_codes
save_rerank_log 실패             → WARNING, 반환값에 영향 없음
```

- 이 메서드는 **예외를 밖으로 내지 않는다**. `_fetch_candidates_for_strategy` 의 fail-closed `except` 에 잡히면 「후보 조회 실패 → 금일 매수 중단」이 되어 결정 8 을 깨뜨린다. 메서드 docstring 에 이 이유를 적는다.
- 「오늘」= `now_kst().date()`, D-1 = 호출자의 `prev_day_str`(`get_previous_trading_day`, 봇은 휴장 달력을 안다). NewsQuant 의 「직전 평일」과 공휴일 뒤에 하루 어긋날 수 있다 — 명부는 SCD2 라 며칠 차이로 라벨이 바뀌지 않는다(무해).

### 5.6 관측

- 전략당 INFO 1줄: `[섹터뉴스] {strategy} mode={mode} reason={reason} 이동 {n}종목(↑{a} ↓{b}) 점수 as-of {HH:MM} 섹터매핑 {m}/{len(codes)}`.
- live 이고 이동 > 0 이면 `candidate_loader` 텔레그램 후보 알림 줄에 `(↑2 261 +0.8)` 표기. shadow 에서는 알림에 손대지 않는다.

---

## 6. 타임라인 (평일 KST)

| 시각 | NewsQuant | 봇 |
|---|---|---|
| 07:40 | Task Scheduler → `run_all_robotraders.bat` [4/5] 기동, 즉시 1회 수집 → **집계 1회** | [5/5] 2초 뒤 기동, 장 전 대기(30초 루프) |
| 07:40~09:00 | 5분 수집 · **10분 집계**(≈8회) | 대기 |
| **09:00** | 1분 수집 · 10분 집계 계속 | **첫 루프 후보 로드**: 스냅샷(D-1) → 코드 → **재정렬(§5)** → 안전필터 → 등록. 읽는 점수는 ≤10분 전 |
| 09:00~15:30 | | 매매 루프 |
| 15:30~ | `trade_date` 가 **다음 평일**로 바뀐다 → 새 키에 쌓이기 시작 | 15:35 리포트 · ~16:01 EOD(스펙 A `sector` 포함) |
| 밤·주말 | 5분/30분 — **프로세스가 살아 있을 때만**(§0) | 유휴 |

---

## 7. 테스트 (전부 red 먼저)

### 7.1 NewsQuant — `tests/` 신설 (pytest, `PYTHONUTF8=1`)

| 파일 | 내용 |
|---|---|
| `tests/test_sector_keywords.py` | YAML 스키마 검증(3자리 키 · name · ko/en · 중복 키워드 거부) · 한국어 부분문자열 · 영어 단어경계(`chip`/`chipotle`) · 대소문자 · `exclude` · 제목/본문 가중 · 본문 2,000자 절단 · 다중 섹터 귀속 |
| `tests/test_sector_news_aggregator.py` | `c` 공식 · 경로 중복 시 max 하나 · `w_src` 기본 0.9 · `n_dir` 가 중립 제외 · sqrt-n · clip ±1 · `MIN_N` 미만 → 0 · 코드 5개 초과 경로 B 건너뜀 + 절단 건수 · 창 계산(월 09:00 → 금 15:30 / 15:31 → 다음 평일 / 토·일) · `top_news` 5건 정렬 · 결정성(같은 입력 → 같은 출력) |
| `tests/test_sector_news_db.py` (`@pytest.mark.db`) | DDL 멱등 · OWNER `robotrader` · UPSERT 멱등(같은 키 2회 → 1행, `computed_at` 갱신) · `news_sector_hit` REPLACE · `get_sector_map_as_of` 왕복 · 함수 부재 시 경로 B off + `n_stock=0`(함수를 임시 스키마에서 감춰 재현) |
| `tests/test_sector_news_api.py` | `/api/sector/news-score` 200 · 잘못된 날짜 400 · 정렬 |

### 7.2 kis-trading-template

| 파일 | 내용 |
|---|---|
| `tests/core/test_sector_news_rerank.py` | max_shift 상한(s=+1 → 정확히 K칸) · 동률 안정성 · 미상 섹터 불변 · `min_abs` 이하 불변 · 양방향 · 중복 코드 ValueError · 빈 입력 · 순열 보존(집합 동일) |
| `tests/test_candidate_sector_news_wiring.py` | `_fetch_candidates_for_strategy` 에 mock provider/repo 주입: `off` 는 repo 호출 0 · `shadow` 는 순서 불변 + `save_rerank_log` 1회(`applied=False`) · `live` 는 새 순서 + `applied=True` · `UndefinedFunction` → 원래 순서 + `fn_missing` · 행 0 → `no_score_rows` · 61분 → `stale` · 저장 실패 → 순서 불변 + WARNING · 예외가 밖으로 안 나감 · `EXCLUDE` 전략 |
| `tests/db/test_sector_news_repo_db.py` (`@pytest.mark.db`) | `ensure_table` 멱등 · UPSERT · `get_scores` 행 0 → `({}, None)` |
| 기존 스위트 | 실패 집합 main 과 양방향 차분 0 |

### 7.3 스펙 A 의존 테스트

`fn_sector_map_as_of` 를 실제로 쓰는 DB 테스트는 스펙 A DDL 이 있는 DB(현재 `kis_template` 에 있음, 0행)에서 돈다. 0행이어도 왕복·타입은 검증된다. 채워진 뒤 값 검증 1건을 추가한다(`005930 → '264'`).

---

## 8. Shadow 평가 (사전 등록) · live 전환

- **기간**: shadow **20거래일 이상**, 스펙 A 부트스트랩 **이후**부터 센다(그 전 행은 `fn_missing` 뿐이다).
- **스크립트**: `scripts/eval_sector_news_shadow.py`(연구 트리 · 읽기 전용 · `resolve_daily_source_db()` 경유). 출력 세 표:
  1. **섹터 점수 유효성** — `sector_news_score.score_signed`(그날 09:00 이전 마지막 `computed_at`) vs 같은 날 `sector_daily_stats.ret_median`(ksic3). Spearman 상관, 상위·하위 5분위 `ret_median` 중앙값 차, n.
  2. **후보 수준** — 전략별로, live 였다면 20위 안에 **들어왔을** 종목(`new_rank ≤ 20 < orig_rank`) vs **밀려났을** 종목(`orig_rank ≤ 20 < new_rank`)의 5거래일 수익률(`daily_prices` close, adj_factor 산술 0) 차와 n. 20위 안 순서 변화만 있는 날은 상위 3 진입/이탈로 같은 표.
  3. **이동 규모·결측** — 일평균 이동 종목 수 · 이동 0 인 날 비율과 `reason` 분포(`no_score_rows`·`stale`·`fn_missing`·약한 점수).
- **live 전환 기준(제안)**: ①의 상위−하위 5분위 차 > 0 이고 부호 일관(20일 중 14일 이상) ∧ ②가 전략 합산 **≥ +0.3%p**(n ≥ 30) ∧ ③의 `stale`+`no_score_rows` 일수 ≤ 3/20. 미달이면 사전(§4.2)·상수(§4.4) 조정 후 shadow 연장. 「없다」 선언은 하지 않는다(표본 부족 — 전문가 자문 §5 와 같은 원칙). **최종 판단은 사장님 결정.**
- 전략별 표를 반드시 따로 낸다(§0 두 축). `deep_mr_dev20` 처럼 부호가 반대로 나오면 `SECTOR_NEWS_EXCLUDE_STRATEGIES` 에 넣는 것이 첫 대응이다.

---

## 9. 롤아웃 순서 · 롤백

| 단계 | 내용 | 조건 |
|---|---|---|
| 1 | 스펙 A 구현·부트스트랩·백필(별건, `feat/sector-data`) | 진행 중 |
| 2 | **NewsQuant 측** 구현(워크트리 또는 브랜치) → 테스트 → 배포. 경로 A 는 A 없이도 동작 → `sector_news_score` 채워지기 시작 | `scheduler.py` 미커밋 diff 정리 먼저 |
| 3 | **봇 측** 구현(`git worktree add -b feat/sector-news-boost D:/tmp/kis-wt-sector-news main`) → 테스트 → EOD 이후 main 머지. 기본값 `shadow` | A 배포 전엔 매일 `fn_missing` 기록만 |
| 4 | shadow ≥ 20거래일 → §8 평가 → 사장님 결정 → `.env` 에 `SECTOR_NEWS_BOOST_MODE=live` | |
| 롤백 | `SECTOR_NEWS_BOOST_MODE=off`(env 1줄, 재기동). 표는 남긴다. 코드 롤백은 `_fetch_candidates_for_strategy` 의 1줄 제거 | |

하우스 룰 승계: 워크트리 작업 · 라이브 트리에서 테스트 금지 · 연구 트리 import 0 · `utils.logger.setup_logger(__name__)` · `utils.korean_time.now_kst()` · 파싱 실패는 `None` · 무징후 절단 금지 · `adj_factor` 산술 0.

---

## 10. 범위 밖 (전부 별건)

- 테마·대장주 분류(KSIC 는 「무엇을 만드는가」다 — 스펙 A §4 와 동일).
- 개별 **종목** 단위 뉴스 부스트(섹터가 아닌 종목 점수). `trading_analyzer` 의 종목 시그널과의 결합.
- 장중 재정렬·재로드 시 재적용(`reload_candidates` 는 그대로 이 경로를 타므로 자동으로 재적용되지만, 장중 점수 변화를 노린 설계는 아니다).
- 시간 감쇠 · 확산도(`duplicate_count`) · 중요도 가중 · LLM 키워드 추출 · 글로벌 뉴스의 종목 매핑.
- NewsQuant 야간·주말 프로세스 생존(운영 이슈. §0 에 기록만).
- `/api/health` 결함(`server.py:73-75`, psycopg2 커넥션에 `.execute`) · `news_stock` orphan 표 정리.

---

## 11. 리스크 · 주의

| 리스크 | 대응 |
|---|---|
| 스펙 A 명부가 비어 있으면 경로 B·봇 매핑이 0 | 결정 10: WARNING + 기록. §8 은 부트스트랩 이후부터 센다 |
| 밤사이 뉴스가 프로세스 부재로 안 쌓임 | 07:40 첫 수집이 RSS·목록 앞 페이지를 긁는다. 창 안 뉴스가 적으면 `MIN_N` 에 걸려 0 → 부스트 없음(안전 쪽). 운영 이슈로 별도 보고 |
| `related_stocks` 노이즈가 섹터 점수를 오염 | 가중 0.7 · 5개 초과 건너뜀 · `news_sector_hit` 로 사후 추적 |
| 큰 섹터(582 소프트웨어 191종목·292 특수기계 169종목)가 뉴스 수로 항상 이김 | `sqrt(n_dir)` 정규화 + `K_SCALE` clip. §8-① 로 검증 |
| 키워드 사전이 주관적 | v1 은 49섹터 · `exclude` · 버전 기록(`dict_version`) · 사전 변경은 커밋으로만 |
| 봇 기동 경로에 DB 왕복 2회 추가 | 09:00 1회 · 두 쿼리 모두 인덱스/함수 1회 · 실측 수십 ms. 예외는 전부 fail-open |
| NewsQuant `scheduler.py` 미커밋 254줄 diff 위에 잡을 얹어야 함 | 단계 2 착수 전 그 diff 의 정체를 확인해 커밋 또는 stash(사장님 확인) |
| 공휴일 뒤 D-1 이 NQ(직전 평일)와 봇(직전 거래일)에서 다를 수 있음 | SCD2 명부라 며칠 차이로 라벨 불변. `trade_date` 는 봇이 휴장일에 로드하지 않으므로 충돌 없음 |

---

## 12. 용어

| 용어 | 뜻 |
|---|---|
| **경로 A / 경로 B** | 뉴스를 섹터에 붙이는 두 방법 — A 는 키워드 사전(제목·본문), B 는 `related_stocks` 종목코드 → 스펙 A 명부 |
| **score_signed** | 섹터 하나의 그날 뉴스 점수, −1(아주 나쁨)~+1(아주 좋음). 방향 있는 뉴스 3건 미만이면 0 |
| **shadow** | 계산하고 기록은 남기되 실제 후보 순서는 바꾸지 않는 모드 |
| **max_shift** | 뉴스가 아무리 좋아도(나빠도) 순위를 움직일 수 있는 최대 칸 수(3) |
| **fail-open** | 이 기능이 실패하면 「원래대로」 진행한다는 뜻. 후보 조회 자체의 fail-closed(실패하면 매수 중단)와 반대 |

---

## 13. v1.1 정정 (2026-09-07 · 구현 계획 작성 중 발견)

결정 10개(§1)는 그대로다. 아래는 계획을 코드 수준으로 내리면서 드러난 정제이며, 두 계획 문서가 이 정정을 기준으로 쓰였다.

| # | 절 | v1 | v1.1 | 이유 |
|---|---|---|---|---|
| 1 | §4.1·§4.5 | 10분마다 항상 UPSERT | **평일 09:05 ≤ now < 15:30 은 쓰지 않는다(동결)** | UPSERT 가 같은 키를 덮어써서 §8-① 「09:00 이전 마지막 계산본」이 남지 않는다. 봇이 09:00 에 읽은 값을 그날 행으로 보존해야 평가가 가능하다. 15:30 부터 다음 거래일 키로 다시 쓴다 |
| 2 | §5.2 | `key = rank − K·s` (실수) | `shift = round_half_away(K·s)` (정수) · `key = rank − shift − 0.5·sign(shift)` · 동률 = 원래 순위 | 편향 없이는 동률에서 원래 순위에 밀려 «혼자 움직일 때» K−1 칸만 간다. 정수 shift + 0.5 편향으로 정확히 K 칸. 여러 종목이 동시에 움직이면 최종 위치 차이는 K 를 넘을 수 있다(상한은 «자기 점수에 의한 이동») |
| 3 | §2.1 | 순수 로직 = `sector_news_aggregator.py` 하나 | `sector_keywords.py`(사전 로드·검증·매칭) + `sector_news_aggregator.py`(창·기여도·집계) + `sector_news_job.py`(오케스트레이션, `db` 를 인자로) | 파일당 책임 하나 · 잡은 MagicMock db 로 단위 테스트 |
| 4 | §4.2 | 「중복 키워드 금지」 | **한 섹터 안에서** ko∪en∪exclude 중복 금지. **섹터 사이 공유는 허용** | 「임상」이 211·212·701 에 다 있어야 「바이오 뉴스가 세 섹터에 동시에 간다」(같은 절)가 성립한다 |
| 5 | §4.4 | `w_src = SOURCE_CREDIBILITY(sentiment_analyzer.py:150)` | 한글 사전 ∪ 영문 사전(`english_sentiment_analyzer.py:115`, 한글이 우선) · 없는 출처 0.9 | 글로벌 출처(cnbc 0.9 · marketwatch 0.85 · investing 0.8 · google 0.75~0.8)가 전부 0.9 로 뭉개지지 않게 |
| 6 | §5.1·§5.6 | `codes = self._apply_sector_news_rerank(...)` · 텔레그램 표기 방법 미정 | `codes, sector_notes = self._apply_sector_news_rerank(...)` · **`CandidateStock.sector_note: str = ""`** 필드 추가(마지막, 기본값) · `bot/candidate_loader.format_candidate_lines()` 가 붙여 쓴다 | 표기를 나르는 통로가 필요했다. 기본값이 있어 기존 생성자 호출 전부 호환 |
| 7 | §3.1 | — | `n_dir < MIN_N` 이어도 **행은 쓴다**(`score_signed=0`) · 귀속 0 인 섹터는 행 없음 | 「뉴스가 없었다」와 「계산이 안 돌았다」를 가른다(§3.1 에 이미 있던 문장을 규칙으로 승격) |

부수: `sector_news_aggregator` 상수에 `DIR_EPS=0.1`(「방향 있는」 문턱) · `TOP_NEWS=5` · `DEFAULT_W_SRC=0.9` 이름을 준다. 봇 상수에 `SECTOR_NEWS_BOOST_MODES` · `resolve_sector_news_mode()` · `SECTOR_NEWS_BOOST_MODE_INVALID`(잘못된 env 값 원문 — 호출자가 WARNING)를 둔다.

---

## 14. v1.2 후속 (2026-09-07 · NewsQuant 측 구현 완료 후 최종 리뷰에서 발견 — 코드가 아니라 스펙·계획의 빈틈)

NewsQuant 측 구현(브랜치 `feat/sector-news-score`, 12+4 커밋)은 §2.1·§3·§4·§7.1 을 그대로 구현했고 실 DB 1회 실행(2026-09-07 08:50 기준 창: 뉴스 605 → 섹터 47, 경로 B on·매핑 0 = 스펙 A 명부 0행)이 통과했다. 그 최종 리뷰가 아래를 «스펙 결함/계획 누락»으로 분류했다. 전부 **별건**이며 v1 동작을 바꾸지 않는다.

| # | 절 | 문제 | 후속 |
|---|---|---|---|
| 1 | §4.2 | 「`ksic_code_name` 이 채워진 뒤 사전 키가 그 표에 없으면 WARNING」이 **어느 태스크에도 없다**(계획 누락). 지금은 표가 0행이라 구현하면 10분마다 49건 WARNING 이 난다 | 스펙 A 부트스트랩 뒤 `sector_news_job` 에 1회/기동 검사 추가(키 ∉ 표 → WARNING 1줄, 중단 아님) |
| 2 | §4.1 | 공휴일 무시 근사가 창을 **좁힌다**(위 §4.1 정정). 연휴(추석·설) 뒤 첫 거래일은 연휴 뉴스가 전부 빠진 채 점수가 난다 | 달력 없이 하는 보정: `window_start = min(prev_weekday(trade_date), trade_date−1) 15:30` 또는 최대 lookback 클램프. §8 평가에서 연휴 다음날은 교란일로 표기 |
| 3 | §13-1 | 동결은 09:05 부터인데 봇은 09:00 에 읽는다. 07:43 기동 → 09:03 실행이 봇이 읽은 행을 덮어쓸 수 있다 | §8 평가 스크립트는 「09:00 이전 마지막 계산본」을 `sector_news_rerank_log.score_asof`·`sector_score`(봇이 실제로 읽은 값)에서 취한다 — `sector_news_score` 행이 아니라. 동결 시작을 09:00 으로 당기는 것도 검토 |
| 4 | §4.4 | `SOURCE_CREDIBILITY` 에 `krx_disclosure: 1.0` 은 있는데 DART 크롤러는 `source='dart'` 로 쓴다(7일 3,503행) → 최대 출처가 기본값 0.9 | `sentiment_analyzer.SOURCE_CREDIBILITY` 에 `'dart'` 키 추가(NewsQuant 감성분석 자체에도 영향 → 별도 검토) |
| 5 | §4.2 | 한글 부분문자열 오탐(유가증권시장·조선일보·무기한·제약 조건 등)이 실측됐다 → 사전 v2026-09-07.1 에서 좁힘(구현 완료). 영어도 transformer/infrastructure/SOC/property/content/carrier 좁힘 | 사전은 `news_sector_hit` 로 계속 튜닝. `dict_version` 이 행마다 남는다 |
| 6 | §3.1 | `computed_at DEFAULT now()` 는 DB 세션 시간대(현재 Asia/Seoul)로 기록된다. 봇의 60분 stale 판정은 KST 벽시계와 비교하므로 DB `TimeZone` 이 바뀌면 조용히 전부 stale 이 된다 | DDL 주석으로 명시(구현 완료). 장기적으로 `timezone('Asia/Seoul', now())` 로 고정 검토 |
