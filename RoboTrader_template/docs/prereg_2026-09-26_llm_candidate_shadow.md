# 사전등록 — LLM 전 종목 채점 shadow «전향 관측» (연구 ② · llm_candidate_shadow)

- 상태: **v0.5 · critic(opus) APPROVE-WITH-FIXES 필수 12 + 권고 채택분 반영 · 동결 대기(2026-09-26 밤)** · 브랜치 `research/dart-events` · 기준 HEAD `b829920` · v0.1(3전략 후보 · m=9)·v0.2(14일 공시 종목) 폐기.
- 🔒 이 문서는 **첫 실행(첫 채점 행) «전»에 커밋으로 동결**한다. 🔒 절은 첫 실행 뒤 바꿀 수 없다 — 첫 실행 «전»이면 개정문 커밋, «뒤»면 새 가족(§5-8 · §13-3).
- 작성 중 조회: 코드 grep/부분 read · DB **SELECT 만**(스키마·행수·작성 시각·입력 커버리지·일별 종목 수 · 채점 규칙 모의 2026-01-02~09-23 179거래일 · 첫 로트 수) · 원장 CSV 행수·표준편차만 · 파일 시각(stat) · `claude --help` · **CLI 모델 호출 = v0.1 의 3회뿐**(부록 B). **LLM 출력과 결과를 잇는 계산 0회**(LLM 출력이 아직 없다).
- 표기: **[실측]** SELECT·로그·CLI·모의 원값 · **[추정]** 외삽 · **[문서]** 코드·기존 문서. ① 인용 = `backtest/concept_axes/candidate_ledger/dart_events/dart_tags.py`(`TAG_TABLE` :29 · `a0c88e2`) · `docs/prereg_2026-09-26_dart_disclosure_events.md`(「① 문서」) · `RESULTS_2026-09-26.md`(`e41c999`).

## 0. 사장님 말 그대로 (2026-09-26 밤 · 관리자 전달본)

> 「① 공시 먼저 + ② LLM shadow」 → 「재료 태그 + 종합 점수」 → 「3전략 룰 통과 전부」 → 「2번(CLI)으로 해야 추가 요금 안내는거 아닌가요?」 → 「승인 — ①부터 착수」 → 「커밋+push 하고 ② 초안 시작」
> v0.1 검정력 문항에: **「설계 재검토」** → **「먼저 어떤식으로 할지 쉽게 설명해줘요」** → 쉬운설명 뒤 **「850개 전부로 가요」**
> 🔒 모델 = **`claude-opus-5-5`** · 🔒 실행 = **T 16:10**(둘 다 사장님 확정)
> v0.2 채점 규칙 문항에: **「자료 변경 시 + 전 종목 20일 순환 (Recommended)」** · 추가: **「1 수집 검사 + 2 검색 팔 5%」**
> 관리자 정정: **「검출선 0.3%p 는 틀렸다 → 첫 로트 기준 0.6~0.8%p」** · 관리자 결정(v0.3 뒤): 트리거 「새 항목」 유지 · (A) 초과분 1일 이월 · 일일 DART 적재 유지 · Q7 = 20거래일 · v0.5 = critic 필수 12 전부 + 권고 채택분.

⇒ 이 문서 = **②** — Claude Code CLI 헤드리스(`claude -p` · **구독 차감 · API 키 없음**)로 **유니버스 전 종목**을 «자료가 바뀐 날» 또는 «20거래일마다» 채점(하루 중앙 ≈ 265종목 [실측 모의 §3-3])해 재료 태그·위험 표시·0~10점을 **저장만** 하고, 봉인 뒤 «LLM 출력이 채점 행 안에서 수익을 가르나»를 잰다.
승계: 09-11 「3전략 + 태쏘만 고도화 · 재무·뉴스로 매수후보 선정 보강」 · ① 결과(자기주식취득 있음(+) +1.46%p · 유상증자/최대주주변경/소송·횡령 있음(−) · CB/BW/EB·공급계약·잠정실적 판별 보류) · 🔒 회의론자 기본 기대 = **「정보 없음」** · 중간 언어 금지.

## 1. 이 문서가 «아닌» 것

- 라이브 변경 0줄 · **봇은 이 데이터를 읽지 않는다**(import 0 · SELECT 0) · 순위·배제 배선 0 · **~2026-10-16 3전략 룰 변경 0건** · 결과는 룰 변경 근거가 아니다(그 뒤에도 별도 사전등록).
- ① 재검정이 아니다: ② = **전향**(모델 학습 시점 < D) · **채점 행 «안» 두 팔의 로트 수익 차**(§7) · 대조군은 절대 수준 보조 인쇄용.
- Anthropic API 호출 아님(키 가드 §5-2) · Claude Code 기본 에이전트 아님(`--safe-mode --tools ""` ⇒ CLAUDE.md·훅·플러그인·MCP·웹 0 · 예외 = 검색 팔 §5-9 만 웹 도구).
- DB 쓰기 = ① 표 `dart_disclosures`(전향 날짜 · ① §2 규칙) + **전용 스키마 `llm_shadow`**(부록 C · 전용 쓰기 역할) 뿐 · INSERT … ON CONFLICT DO NOTHING · retention 0 · 공시·뉴스 «본문»·뉴스 점수 열은 입력 금지.

## 2. 시점 🔒

- **T** = 실행일(거래일 판정 `utils/korean_holidays` · 12-31 휴장 포함) · **D = `daily_prices` `stock_code='KOSPI'` 의 최대 날짜 < T** · **u**(진입일) = 개봉 때 KOSPI 달력에서 D 다음 날. 본체 = **T 16:10**(🔒 사장님) · 검색 팔 = **T 08:30**(§5-9) · 순서: ① `dart_disclosures` 적재 ② `_plan` 기록 ③ 채점 ④ 원장 해시.
- 3전략 전수 스냅샷(`cand_strategies` 플래그용 · 채점 조건 아님)은 **T 09:00:2x 에 생긴다** [실측 DB 2026-07-01~09-22 56일 × 3전략 2,749행 전부 다음 거래일 09:00:05~09:00:39 · 코드 `main.py:438` → `bot/candidate_loader.py:58` → `bot/liquidation_handler.py:584`(`:604`) → `runners/screener_snapshot_collector.py:82`(`:121`) → `db/repositories/candidate.py:143-152`] · 전수 저장 발효 09-28 07:40(`2274895` · `config/constants.py:200-201`) · **스냅샷 없는 날도 채점**(`cand_strategies` NULL).
- 🔒 PIT 는 실행 시각이 아니라 **입력 컷오프**(§3-5)로 지킨다. 관측 시작 = 🔒 코드 커밋 뒤 첫 T 의 D · 소급 채점 금지 · 누락 보충 = 최근 5거래일 · **D 오름차순**.

## 3. 채점 대상 · 입력 계약 🔒 (단위 = 채점 행 (D, g) · 같은 종목은 하루 1회)

**3-1 유니버스** `U(D)` = `daily_prices` D 행 `market_cap IS NOT NULL` ∧ `replayer/loader.py:28-29 STOCK_ONLY` ∧ `classify_exclusions`(`:81` · 우선주·외국·리츠·스팩·ETF · ① §6 과 같음) · 공시 조건 **없음**. [실측] 중앙 2,493(04-01~09-23) · 2,544(08-03~09-23).
**3-2 채점 조건** 🔒 — 둘 중 하나(둘 다면 `trigger='A'` · (A) 로 채점된 종목은 그날 조각이어도 (B) 아님):
- **(A) 자료 변경** = D′(= 직전 거래일) 이후 g 에 **새 B·I 원공시**(`dart_disclosures` · `rcept_dt ∈ (D′, D]` · ① §3-2 `is_corr=False` · 태그 무관) **또는 새 기사**(`news` `source <> 'dart'` · `news_stock.news_id = news.id` · `published_at ∈ [D′+1 00:00, D+1 00:00)` ∧ `created_at < T 08:30`).
- **(B) 순환** = 마지막 **ok** 채점 뒤 **20거래일** 경과(Q7 ✅) · 가족 첫 20거래일은 조각 `k = int(sha256("20261004:" + family + ":" + code), 16) mod 20` 을 k 번째 날(0부터) · 뒤에 들어온 종목은 첫날 (B) · **순환 상태·조각은 가족별**.
- 🔒 **선언된 이탈 — 입력 해시 전체가 아니라 «새 항목»만 방아쇠**(✅ 관리자 승인): 해시 전체면 창에서 제목이 빠지는 날·재무 PIT 교체일(전 종목 · [실측] 04-01·04-10·06-01·08-31 각 2,091~2,261)·시총 5분위 경계 이동([실측] 중앙 56/일)·news(dart) 전 유형(B·I 의 1.6배)이 모두 방아쇠가 된다.
- [실측 · 08-03~09-23] 새 B·I 원공시 종목 **중앙 110/일**(① 원공시 규칙 · ∩U · critic 값 115 와 정의 차이) · 새 기사 종목 116/일 · 🔴 기사 링크는 2026-03~07 거의 0(월별 링크 뉴스 3월 0 · 4월 62 · 5월 28 · 6월 0 · 7월 80 · 8월 2,444 · 9월 7,107) ⇒ 그 구간 모의의 (A) 는 공시 위주(과소).
**3-3 상한 · 우선순위 · 성수기** 🔒 — 1차 채점 ≤ **360종목/일**(§5-4). 순서 = ① 전날 이월된 (A) ② 그날 (A) ③ (B)(가장 오래 밀린 순 → 조각 → 코드). ①·② 가 넘치면 `default_rng([20261004, 87, yyyymmdd(D)])` 로 채우고 못 든 (A) 는 **다음 날 1회 이월**(`carried=true`) · 이월된 날에도 못 들면 `dropped_carry` 행(탈락 · 인쇄). **성수기 날** 🔒 = ①+② ≥ 360 인 날(결산·주총 · 결과 전 판정) ⇒ 그날 (B) 정지 · (B) 는 제한 없이 이월 · 성수기 날 제외판 = 보조 인쇄.
- `skipped_cap`·`parse_error`·`timeout` 은 순환 시계·에피소드를 **리셋하지 않는다**(ok 만 채점).
- [실측 모의 · 이 규칙 · 2026-01-02~09-23 179일] 하루 채점 **중앙 265**(p90 360 · (A) 175 · (B) 55) · 호출 중앙 15(최대 19) · 첫 로트 중앙 146/일 · **성수기 날 23일**(02-05·06 · 03-11~04-01 16일 · 04-30 · 05-29 · 06-01 · 09-14·15) · 이월 22일(최대 554) · **탈락 740종목**(전부 결산 시즌) · (B) 적체 최대 200. 결산 시즌(02-16~04-15 39일): 채점 312 · (A) 278 · (B) 7 · 호출 17 · 첫 로트 193/일. 08-03~09-23: 채점 279 · (A) 215 · (B) 58 · 첫 로트 140/일.
**3-4 전향 공시 적재** 🔒 — ① 스크립트 `scripts/dart_disclosure_backfill.py` 를 **잠금만 교체해 재사용**(선언된 이탈 · 나머지 로직 그대로): 잠금 = `msvcrt.locking` OS 잠금 파일(프로세스가 쥐고 있는 동안만 유효) + 파일에 PID·생성 시각 · 소유 프로세스가 죽었으면 **자동 해제**(stale) · 본체·검색 팔 공유. 범위 = 마지막 적재일 다음 날 ~ D · ① 문서 §2 완결 판정 · 미완결이면 그 D 채점 보류.
- OpenDART 상한 = **두 프로세스 합산 ≤ 60회/일**(`call_log.jsonl` 날짜별 집계 인쇄) · [실측 적재본 2024-03~2026-09 · 실행 1회 = 날짜×유형 페이지 합] 중앙 4 · p90 9 · 최대 15 · 키(`.env OPENDART_API_KEY`) 출력·로그 금지 · 날짜는 `rcept_dt` 만(🔴 `rcept_no` 앞 8자리 금지).
- 🔒 **경보**: 적재 실패 · 그날 채점 0행 · `model_mismatch` · exe 해시 불일치 ⇒ 텔레그램 1통(`config/key.ini` `[TELEGRAM]` token·chat_id 재사용 · 런너가 직접 보냄 · 봇 프로세스 무관 · 본문에 점수·태그 금지).
**3-5 PIT 컷오프(두 팔 공통)** 🔒 — `news.published_at < D+1 00:00`(D 이하) ∧ **`news.created_at < T 08:30`** · KST · (A) 공시 조건은 `rcept_dt ≤ D`. 본체 손실(09:00 컷 대비) [실측 08-03~09-23]: (A) 종목 평균 0.4/일(중앙 0) · 입력 제목 평균 1.5건/일(critic 추정 ≈ 4).
**3-6 공시 제목** — `news` `source='dart'` JOIN `news_stock` ON **`news_stock.news_id = news.id`**(🔴 `news.news_id` text 조인 금지 · [실측] 링크 515,039행 중 `n.id` 조인 515,039 · `n.news_id` 0) · 최근 10거래일 · 제목 `[corp_name] report_nm`(NewsQuant `dart_crawler.py:76`) ⇒ 앞 `[…] ` 떼고 공백 연속 → 1칸 · `published_at` = 수집 시각(`:138-160`) · 커버리지 [실측 09-01~09-23] 16일 99.4~100% · 09-07 53.3% · 「(A) 공시로 채점됐는데 공시 제목 0건」 종목 수 매일 인쇄.
**3-7 기사 제목** — 같은 조인 · `source <> 'dart'` · 최근 5거래일 · `- MM-DD [출처] 제목` · [실측 09-01~09-23] naver_finance 5,249 · hankyung 1,150 · mk_news 537 · 수집 지연 중앙 6분 · p95 14시간.
**3-8 종목당 입력 상한** — 같은 제목 중복 제거 · 최신순 · **공시 ≤ 12 · 기사 ≤ 8 · 제목 ≤ 120자** · 전체 건수 따로 ⇒ 블록 ≤ ≈ 1,000 토큰 · 보통 ≈ 400 [추정].
**3-9 재무** — `kis_financial_ratio` **`div_cls='1'`** [실측: 적재 시각 열 없음 · `per` 202606 비결측 0 ⇒ 제외] · 8개 = `stac_yymm`·sales_growth·operating_income_growth·net_income_growth·roe_value·liability_ratio·reserve_ratio·eps · PIT = 월말 + 60일(03·06·09) / 100일(12) ≤ D 최신 1행(`multiverse/data/pit_reader.py:460` 연간 보수화 · 선언된 이탈).
**3-10 가격 맥락(최소)** — 시장 · 시가총액(D · 억원) · 20거래일 수익률(원시 종가 · 창 안 `adj_factor ≠ 1` 이면 N/A) · 종목명(`stock_info` → 공시 `corp_name` → 코드). 전략·순위·채점 이유((A)/(B))는 입력에 넣지 않는다.

## 4. 출력 · 저장 · 봉인 집행 🔒

- 태그 사전(정의 = 부록 A.1): **catalyst_tags** = ① 7태그(`dart_tags.py:29-38` 이름 · 가운뎃점 U+00B7) + `실적개선`·`수주`·`신사업`·`기타`·`없음` · **risk_flags** = `유상증자`·`CB/BW`·`소송`·`최대주주변경`·`감사의견`·`관리종목`·`기타`(없으면 []).
- 호출 1회 = ≤ 20종목 · 출력 `items[]`(`code`·`catalyst_tags`·`risk_flags`·`score` 0~10·`rationale` ≤ 200자) · 스키마 A.3 + 사후 검사(code 집합 일치 · `없음` 단독 · 중복 없음).
- 행 시스템 필드: `model`(`modelUsage` 유일 키 = `canonicalModel` [실측]) · `cli_version` · **`exe_sha256`** · **`code_sha`** · **`argv_sha256`**(인자 리스트 UTF-8 해시 · 시스템 프롬프트·스키마 포함) · `prompt_version` · `prompt_sha256` · `input_sha256` · 지연 · `cost_usd`(`costBasis: list` 정가 환산 · 구독 청구 아님 [추정]).
- 저장 = **전용 스키마 `llm_shadow`**(부록 C 초안): `shadow`(본표 · PK (family, scan_date, stock_code) · `trigger`·`slice`·`gap_td`·`carried`·`cand_strategies`·`status`·`batch_id`·`batch_pos`·`input_text`·`output_json`) · `plan`(§5-3) · `batch`(호출 1행 · `raw_result`·`api_error_status`·`error_text`) · `rep`(반복) · `search`(검색 팔) · `search_daily_agg`(검색 팔 (ㄱ)(ㄷ) 집계 · 허용). **쓰기 = 전용 역할 `llm_shadow_writer` 만** · `robotrader` 에는 **허용 집계 뷰만** GRANT(Q10).
- 🔒 **봉인 대상(개봉-2 전 열람 금지 · §13-1)**: `shadow.output_json` · `batch.raw_result` · `rep` 전부 · `search` 의 출력·`sources` 원문(허용 = §5-9 집계 뷰) · 런너 로그(🔒 로그에는 건수·status·`error_text` 만 · 모델 출력 금지). `parse_error` 디버깅은 **`error_text` 만**(CLI·검증기 메시지 ≤ 300자 · 모델 출력 인용 금지).
- 🔒 **원장 해시** — 매 실행 끝: 그날 D 의 `llm_shadow` 모든 표 행을 정렬된 CSV 로 내보내 `D:/research-archive/llm_shadow/<D>/` 에 저장 + `(D, 표, 행수, sha256)` 를 `D:/research-archive/llm_shadow/ledger_sha256.txt` 에 **append**(덮어쓰기 금지) · 개봉 때 DB 행과 재대조.

## 5. 실행 규약 🔒

**5-1 프로세스 · 무결성** — 런너 `RoboTrader_template/scripts/llm_candidate_shadow.py`(본체) · `…/llm_shadow_search.py`(검색 팔) = **별도 프로세스**(봇 import 0 · KIS API 0 ⇒ 프로세스별 API 락 무관) · 작업 스케줄러 `kis-llm-candidate-shadow`(월~금 16:10 · 90분 제한) · `kis-llm-shadow-search`(월~금 08:30 · 08:58 강제 종료) · 같은 Windows 사용자 · 로그온 시에만 [추정] · 실행 위치 = 전용 워크트리 · 🔒 **HEAD = 코드 커밋 sha(상수) ∧ `git status --porcelain` 빈 상태에서만 실행** · 아니면 거부 + 경보.
**5-2 CLI 고정 · 호출** 🔒 — 런너 전용 경로에 **`npm install --prefix %LOCALAPPDATA%\kis-llm-shadow\cli @anthropic-ai/claude-code@2.1.283`** 고정 설치 · 호출 = `…\cli\node_modules\@anthropic-ai\claude-code\bin\claude.exe` 를 **`subprocess.run([exe, …], shell=False)` 리스트 인자로 직접**(`.cmd` 셸 래퍼 금지) · env `DISABLE_AUTOUPDATER=1` · **exe sha256 을 호출마다 기록 · 동결 값과 다르면 실행 거부**. 근거 [실측 stat]: 이 PC 전역 CLI `…\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe` 가 **2026-09-26 18:04:58 에 교체**됐다(옛 파일 `claude.exe.old.*` 09:59:39 · 자동 업데이트) ⇒ 전역 CLI 는 발밑에서 바뀐다.
- 가드: `ANTHROPIC_API_KEY`·`ANTHROPIC_AUTH_TOKEN` 있으면 **즉시 중단**(API 과금 경로) · `CLAUDECODE`·`CLAUDE_CODE_*` 제거 — **예외 `CLAUDE_CODE_OAUTH_TOKEN`**(구독 인증일 수 있어 유지) · 잠금(§3-4 와 같은 방식 · 두 번째 프로세스 즉시 종료).
- 🔒 **전달 검증 dry-run 1회**(구현 때 · 가상 입력): 모델에게 A.1 마지막 줄과 catalyst enum 개수(12)를 되읊게 해 Windows 인자 전달이 온전함을 확인 · 실패면 첫 실행 금지.
**5-3 상태 기계** 🔒 — 호출 «전»에 그날 계획을 `plan` 에 INSERT(`family`·D·code·`trigger`·`carried`·`batch_id`·`batch_pos`·`U(D)` 코드 목록 sha256) → 호출 → `shadow` 결과. 재개(크래시·놓친 실행)는 `plan` 에 있고 `shadow` 에 종결 status 가 없는 칸만 · D 오름차순 · 이미 있는 칸은 절대 재호출 안 함. **채점 = status `ok`** · `carried` 열 · `dropped_carry` 행.
**5-4 묶음 · 상한 · 재시도** — 그날 `plan` 목록을 `default_rng([20261004, 82, yyyymmdd(D)])` 로 섞어 20개씩(`batch_pos` 기록) · 하루 **≤ 20호출** = 1차 ≤ 18묶음(360) + 반복 1 + 재시도 1 · 재시도 = 실패 종목을 모아 한 묶음(`default_rng([20261004, 91, yyyymmdd(D)])` 순서 · 단건 대신 묶음 = 선언된 이탈) · 동시 ≤ 3 · 묶음 타임아웃 = **dry-run p95 로 정해 첫 실행 «전» 개정문**(잠정 180초). `modelUsage` 키 ≠ 가족 모델 ⇒ `model_mismatch` + 그날 중단(`--fallback-model` 금지).
**5-5 한도 오류** 🔒 — 한도 = `is_error` ∧ `error_text`·`result` 가 정규식 `(?i)\b(usage limit|limit reached|rate limit(ed)?|quota( exceeded)?|too many requests)\b` 에 맞음 · 기록 = `batch`(`api_error_status`·`error_text`·`created_at`). **`api_error_status` 429·529(과부하)는 180초 뒤 1회 재시도 · 따로 집계 · 사다리 판정에서 제외**.
**5-6 반복(결정성)** — 온도 조절 없음 ⇒ 1차 `ok` 중 `min(20, ceil(0.05·n_ok))` 개(`default_rng([20261004, 83, yyyymmdd(D)])`)를 새로 섞은 묶음(`[20261004, 90, yyyymmdd(D)]`)으로 1회 더 → `rep`.
**5-7 해시** — `prompt_sha256` = sha256(UTF-8(A.1 + "\n" + A.2 + "\n" + A.3)) · 블록 = 부록 펜스 안 본문(끝 줄바꿈 제거) · 런너 상수 ≠ 부록 ⇒ 거부.
**5-8 구독 한도 사다리** 🔒 — 가족 **F1** opus·전 규칙 → **F2** `claude-sonnet-5`·전 규칙 → **F3** opus·(A) 만((B) 중단 · [실측 모의 v0.3] 첫 로트 ≈ 94/일) · 가족 = (모델, 규칙) · 섞기·풀링 금지 · 옛 행 보존 · **판정 가족 = 120 D 를 먼저 채운 가족 하나**(나머지는 보조 인쇄). 한도 오류(§5-5)가 나면 **검색 팔(§5-9)을 먼저 중단**. **시운전** = 각 가족의 첫 3거래일 · 기준 = Q6(관리자 권고 = 한도 오류 하루 2회 이상 또는 이틀 연속 ⇒ 다음 단계) · 시운전 뒤 한도 오류는 기록만 · 단계 변경은 개정문 + 사장님.
- 예상 [추정 · 모의 채점 수 기준]: 하루 14~19호출 · 입력 ≈ 265 × 400 + 15 × 2,000 ≈ **0.14M 토큰/일**(최대 0.4M) · 출력 ≈ 265 × 250~500 ≈ **65~130k**(출력은 첫 추정의 2~4배로 본다) · 벽시계 ≈ 10~25분(동시 3) · 시운전 3일 실측으로 EOD 갱신.
**5-9 검색 팔(search arm)** 🔒 — 가족 **S1** · `claude-opus-5-5` · **판정 밖(보조만)** · 목적 = ① NewsQuant 수집 누락 측정 ② DB 만 본 본체 점수 vs 웹을 본 점수.
- 실행 T 08:30 · **08:58 에 남은 호출 강제 종료**(`timeout`) — 검색이 전부 T 09:00(매수 시점) 전에 끝나야 사전정보 규약이 선다 · 목록 = §3-2·3-3 과 같은 코드(같은 08:30 컷) → `k = min(15, max(5, round(0.05·n)))` 종목을 `default_rng([20261004, 88, yyyymmdd(D)])` 로 코드 정렬 목록에서 비복원 추출 · 호출 순서 `[20261004, 92, yyyymmdd(D)]` · **단건 호출** · 입력 = 본체와 같은 종목 블록(A.2 · 1종목) · 시스템 = A.1 규칙 2) → **A.5** · 스키마 **A.6** · 명령 **A.7** · 재시도 1회(하루 최대 30호출).
- 🔒 **짝** = 검색 팔 블록과 본체 블록의 해시(`=== {i}/{k}` 머리줄 뺀 종목 블록)가 같을 때만 · `in_main` 은 개봉 때 파생(매일 쓰지 않음) · **모델 검사** = `modelUsage` 중 출력 토큰이 가장 많은 키 = `claude-opus-5-5`(도구가 다른 모델을 부를 수 있어서).
- 도구 이름: `WebFetch` = [문서 `claude --help` `--restricted` 설명 :201] · ⚠️ **`WebSearch` 는 help 에 이름 없음**(근거 = `usage.server_tool_use.web_search_requests` [실측]·Claude Code 도구 목록 [문서]) ⇒ dry-run 에서 `web_search_requests ≥ 1` 확인 · 권한 거부(`permission_denials`)면 `--allowedTools WebSearch,WebFetch` 추가(미시험 · 첫 실행 «전» 개정문).
- 🔒 **자동 집계(개봉 무관 · 허용 · §13-1)** — (ㄱ) **수집 누락 추정**(매일 · **D+3 에 판정** = 늦은 적재를 기다림) = `sources[]` 중 date ≤ D 인데 DB 에 없는 수(공시/기사 · 비율). 제목 정규화 = NFKC → 공백 제거 → 가운뎃점 6종 → `·`(① 문서 §3-1 ②) → 앞머리 `[…]` 반복 제거 → 따옴표·괄호·`…,.!?:;~-` 제거 → 영문 소문자. **공시** = URL `rcpNo` ∈ `dart_disclosures.rcept_no` 또는 `news` url · 없으면 같은 종목·`rcept_dt` ±1일 `report_nm` 정규화 일치. **기사** = `news`(dart 제외) `published_at` ±1일 · 정규화 제목 일치 또는 15자 이상 포함 · 매칭되나 이 종목 링크 없음 = 「DB 있음·링크 없음」 따로. (ㄴ) **점수 차 분포**(짝의 `검색 − 본체` 평균·sd·|차| ≥ 3 비율·n) = **누적만 · 개봉-1 에 인쇄**. (ㄷ) `excluded_after_D[]` 건수 · date > D 인데 `sources` 에 든 건수(매일).
- 검정 = 개봉-2 보조 인쇄만(검색 팔 점수 상·하위 1/2 로트 차 · 본체 첫 로트와 짝 · CR1) · 비용 = 하루 **11~15호출(최대 30)** · 호출당 10~40k 토큰 · 30~120초 [추정 · 시운전 실측].

## 6. 결과(outcome) 🔒 — 개봉 때만 계산 · ① 문서 §6 규약 인용

- 로트 = 채점 행(ok): **진입 u 시가**(원시) · qty = `arm_b_qty`(`ledger8/sizing.py:67`) · 밴드 없음 · **청산 = ma20 규칙**(`ledger8/exitsim8.py:175 simulate_lot` · `sellprobe8.py:45 resolve_live_tp_sl('book_pullback_ma20', …)` = (0.10 · 0.08 · 50) 아니면 중단 · `strategies/book_pullback_ma20/config.yaml:31-33` · `SellProbe` `:67` · window_fn `date < day` · 손절 우선 · 동결 blob).
- 🔒 **에피소드** = 같은 g 의 직전 **ok** 채점과 간격 ≤ 5거래일이면 같은 묶음 → **첫 행만** ⇒ (B) 는 항상 첫 행 · (A) 연속은 접힘. [실측 모의 · 120거래일 창 3개(시작 01-02·02-02·03-03)] 첫 로트 **19,302~19,709** · 접힌 비율 31.6~37.1% · 첫 20일 3,109~4,793 · 이후 중앙 134.5~156.5/일 · 성수기 날 19~21 ⇒ **N ≈ 19,300~19,700** [추정 · 기사 결손 구간 포함].
- 상한 u + 50 ≤ 마지막 봉 · R3 u 시가 없음/≤0 · R4 `impossible_bar`(`replayer/flags.py:88 compute_bar_flags`) · R5 `exit_reason=open`·봉 끊김(상폐 포함).
- 🔒 **비대칭 규칙(② 식)**: **팔 배정 = 제외 «전» ok 첫 로트 전체** · 팔별 제외율 = (R3+R4+R5) / 그 팔 첫 로트 · **R1 없음**(전향이라 U(D) 에 있던 종목) · 「그날 첫 로트 < 3 인 날 제외」도 **제외 전** 판정 · 제외율 차 > **2%p** ⇒ 제외 많은 팔이 위 팔이면 「없음」·「있음(+)」 금지 · 아래 팔이면 「없음」·「있음(−)」 금지.
- **대조(보조 · 절대 수준)** = ① 문서 §6 방식 · 풀 = U(D) ∖ (그날 채점 행) ∩ 같은 시총 5분위 ∩ u 시가 > 0 · 1:1 × 20(`default_rng([20261004, 81, k])` · 처리 순서 (u, code) · 재추출 같은 rng) · 팔별 「채점 행 − 대조」 인쇄만. 결과 = `ret_pct`(gross) · net −0.25 병기 · 원 정수.

## 7. 검정 · 라벨 🔒 (개봉-2 · 판정 가족 하나의 ok 첫 로트)

- δ = **채점 행 안 두 팔의 로트 평균 수익 차**(위 − 아래 · %p/로트 · **날짜 고정효과**: 같은 D 안 비교를 D 별 가중 평균 = 팔 더미 + D 더미 회귀 계수) · **가족 m = 3 · Holm · K = 3.24**:
  - **T1 고정 절단** 🔒 = 점수 **≥ 6 vs ≤ 4**(5점 = 중립 · 제외 · 5점 비율 인쇄) · **T2** `catalyst_tags ≠ [없음]` vs `[없음]` · **T3** `risk_flags ≠ []` vs `[]` · 이진 1 → 위 팔.
- 도구 = K2 승계(`candidate_ledger/tool_calibration/RESULTS.md:57` · P2 에피소드 첫 로트 · 날짜 안 비교 · 그날 첫 로트 < 3 인 날 제외 · CR1 종목 클러스터) · `status ≠ ok` 는 표본 밖(건수 인쇄).
- 🔒 **가짜 게이트**(검정마다 j = 1…400 · 판정 전): LLM 출력을 날짜 안에서 `default_rng([20261004, 84, t, j])` 로 순열 → 같은 도구 · `p<0.10` 거부율 **≤ 0.13** ⇒ CR1 · 초과 ⇒ 2원 클러스터(종목 × u 20거래일 블록 · CGM · `prereg_2026-09-26_exit_bracket_pair_comparison.md:74`) · 둘 다 초과 ⇒ 판별 보류(도구) p = 1.
- 라벨 = ① 문서 §7: **있음(+/−)** Holm(m=3) p < 0.05 ∧ |δ| ≥ **0.4%p** · **없음** 95% CI ⊂ (−0.4, +0.4) · **판별 보류** 그 밖(어느 팔이든 n < 30 ⇒ p = 1) · 비대칭 제한(§6).
- 보조(인쇄만 · 판정 금지 · 가짜 시드 `[20261004, 94, t, j]`): **T1 3분위판**(날짜 안 `rank(pct, average)`) · **T4** = 규칙 태그 `자기주식취득`(`rcept_dt ∈ [D−4, D]`) 첫 로트 안 LLM 점수 상·하위 1/2(20거래일 블록 안 분할 · 검정력 낮음 결과 전 인정) · **r20 3분위 × 시총 5분위 층 안 T1** · `trigger` A/B 별 · `cand_strategies` 별 T1(순위 층 참고) · 성수기 날 제외판 · 규칙 7태그 열(`[corp_name] ` 떼고 `dart_tags`) · 대조 대비 절대 수준 · `batch_pos` 별 · 반복 불일치 제외판 · 검색 팔 상·하위 · 판정 밖 가족 · 반창.

## 8. 개봉 일정 · 검정력 🔒

- 관측 창 = 판정 가족 첫 D 부터 **120거래일**. 🔒 **개봉-1** = 60번째 D 뒤 — **검정력만**: 날짜별 행수·status·커버리지·한도 오류·반복 일치율·검색 팔 (ㄱ)(ㄷ) + **(ㄴ) 누적** · 팔 n · 5점 비율 · 결과 sd(LLM 출력으로 나누지 않음 · 완결 로트만) · 가짜 SD_null·거부율(`[20261004, 93, t, j]`) · MDE. 🔴 δ·p·팔별 평균·LLM 출력과 결과의 어떤 연관도 인쇄 금지.
- 🔒 **개봉-2** = 120번째 D → u → ma20 50 → +1거래일. 날짜 [추정 · `utils/korean_holidays` + **12-31 휴장 반영**]: 첫 D = 2026-09-23 이면 **개봉-1 = 2026-12-22**(60번째 D 12-21) · **개봉-2 = 2027-06-07**(120번째 D 2027-03-23 · u 03-24 · +50 = 06-04). 늦게 시작하면 같은 산식.
- 사전 MDE [추정 · N = §6 모의 · sd = ① 대조 sd 6.6~7.2(`dart_events/results/sealed_report.md:27-33`) · K = 3.24(Holm m=3 1단계 z 2.39 + 0.84) · 날짜 효과 = 설계효과 1 · 5점 외 점수는 위·아래 반반 · T2 재료 30% · T3 위험 5% 가정]:

| 검정 · 시나리오 | N 19,300 팔 n | MDE %p | 1.96·SE | N 19,700 팔 n | MDE %p | 1.96·SE | 없음 가능 |
|---|---|---|---|---|---|---|---|
| T1 · 5점 50% | 4,825 / 4,825 | 0.43~0.47 | 0.26~0.29 | 4,925 / 4,925 | 0.43~0.47 | 0.26~0.28 | 예 |
| T1 · 5점 70% | 2,895 / 2,895 | 0.56~0.61 | 0.34~0.37 | 2,955 / 2,955 | 0.56~0.61 | 0.34~0.37 | 예 |
| T1 · 5점 85% | 1,448 / 1,448 | 0.79~0.87 | 0.48~0.52 | 1,478 / 1,478 | 0.79~0.86 | 0.48~0.52 | 아니오 |
| T2 재료 30% | 5,790 / 13,510 | 0.34~0.37 | 0.20~0.22 | 5,910 / 13,790 | 0.33~0.36 | 0.20~0.22 | 예 |
| T3 위험 5% | 965 / 18,335 | 0.71~0.77 | 0.43~0.47 | 985 / 18,715 | 0.70~0.76 | 0.42~0.46 | 아니오 |
| (보조) T1 3분위 | 6,433 / 6,433 | 0.38~0.41 | 0.23~0.25 | 6,567 / 6,567 | 0.37~0.41 | 0.23~0.25 | (보조) |
| (보조) T4 자사주 | 178 / 178 (v0.3 실측 356) | 2.26~2.47 | 1.37~1.50 | — | — | — | (보조) |

- ⇒ 🔒 **결과 전 인정**: 「없음」은 **조건부** — T1 은 5점 비율 ≲ 74~78% 일 때만(팔당 ≥ 2,100~2,500 필요) · T2 는 가능 · T3 는 불가 · 「있음」은 T1 |δ| ≳ 0.43~0.87 · T2 ≳ 0.34~0.37%p · 하루 ≈ 146 첫 로트가 같은 시장을 공유 ⇒ 설계효과 > 1 이면 나빠진다(가짜 게이트·2원 SE 가 잡는다) · F3 로 내려가면 T1(5점 70%) MDE ≈ 0.73~0.80.

## 9. 한계 선언 🔒

1. **비결정성·묶음 문맥** — 온도 없음 · 반복 5% 로 일치율만 · 같은 묶음끼리 상대 평가 가능(무작위 묶음 + `batch_pos` 인쇄로만 대응).
2. **모델 사전지식** — 종목명을 준다(전향이라 D 이후 정보는 아님) · 「입력만 근거」는 강제가 아니다.
3. **모델 변동** — 서비스 쪽 교체·은퇴(→ `model_mismatch`·중단) · CLI 는 고정 설치로 막는다(§5-2).
4. **입력 결손·출처 불일치** — (A) 공시 조건은 `dart_disclosures`, 제목은 news(dart) · 09-07 53% · 🔴 기사 링크 2026-03~07 결손 ⇒ 다시 끊기면 (A) 가 줄고 (B) 가 는다 · 재무 지연 · 제목만.
5. **채점 조건 자체가 선택** — (A) 행 = «새 자료가 붙은 날» · (B) 행 = «20일 동안 새 자료 없던 종목» ⇒ 두 모집단이 섞인다(`trigger` 별 보조 · 날짜 고정효과는 날짜 효과만 제거).
6. **에피소드 연쇄** — [실측 모의] 채점 행의 31.6~37.1% 가 접힌다 · 창 전체를 한 에피소드로 잇는 종목은 0(종목당 중앙 8 에피소드) · critic 산출(55.9% 접힘 · 70종목 1에피소드)은 재현되지 않았다(정의 차이 추정) — 뉴스가 잦은 종목은 «첫날 점수»만 쓴다.
7. **ma20 청산 공통 적용** — 측정 규약 · gross · 일봉 · 시가 진입 · 밴드 없음.
8. **성수기 절단·이월** — 모의 탈락 740종목(전부 결산 시즌) · (B) 정지로 순환 간격이 20일보다 길어짐 · 결과와 무관하나 표본이 준다(성수기 제외판 보조).
9. **단일 국면 · 보수적 컷오프** — 관측 ≈ 6개월 · 금요일 밤·주말 기사는 버리고 T 08:30 뒤 적재분도 버린다.
10. **구독 한도** — 사람의 대화형 사용과 한도 공유 · 결측은 날짜 단위.
11. **검색 팔** — 재현 불가(`sources[]` 는 자기보고) · D 이후 자료를 실제로 걸렀다는 보장 없음 · 5~15/일 · **T 08:30 실행은 봇 07:40 기동 뒤 장 전 준비와 PC 자원(CPU·메모리·네트워크·DB)을 나눈다**(별도 프로세스 · KIS API 락 무관 · 08:58 종료).

## 10. 산출물 · 순서 🔒

- `backtest/concept_axes/candidate_ledger/llm_shadow/`: `prompt_v1.py`(A.1~A.3·A.5·A.6 · 해시) · `inputs.py`(§3) · `schedule.py`(§3-2·3-3 · 조각 · 이월 · 성수기) · `state.py`(§5-3 plan·재개) · `search_arm.py`(§5-9 · 정규화 매칭 · 집계) · `ledger.py`(원장 해시) · `tests/test_llm_shadow.py`(해시 = 부록 · 컷오프 경계 · (A) 새 항목 · 조각·첫 20일 · 이월 1회·탈락 · 성수기 · 재개 멱등 · 리셋 안 함 · 묶음/시드 · 사후 검사 · 한도 정규식·429/529 · 잠금 stale · 키 가드·OAuth 예외 · exe 해시 거부 · 더러운 워크트리 거부) · `run_unseal.py --stage power|verdict` · `results/` · `RESULTS_<날짜>.md` · 런너 2개.
- 순서: ① critic → **동결 커밋** → ② 코드 + 테스트 **🔒 코드 커밋**(sha 를 런너 상수로) → ③ DB 역할·스키마 생성(Q10 · postgres) → ④ CLI 고정 설치 + exe sha256 동결 → ⑤ dry-run(가상 입력 · CLI ≤ 10회 · 전달 검증 · 묶음 p95 · WebSearch) → 타임아웃·도구 개정문 → ⑥ 작업 스케줄러 2개(사장님 확인) → ⑦ F1·S1 시운전 3일 → 사다리 판정 → ⑧ 매일 → ⑨ 개봉-1 커밋 → ⑩ 개봉-2 `RESULTS` 커밋 → ⑪ verifier.

## 11. 검증 (verifier 1회 · 개봉-2 뒤) 🔒

- **V1 시점·조건** — 런너 시작 ≥ 16:10 / 08:30 · 검색 팔 종료 < T 09:00 · D = KOSPI 최대 날짜 < T · `plan` ↔ `shadow` 대조(재개 멱등 · 재호출 0) · `trigger`·이월 1회·성수기 재계산 · 한도 오류·429/529 재집계 · OpenDART 일 합계 ≤ 60.
- **V2 고정** — 모든 행 `prompt_sha256` = 부록 · `exe_sha256`·`code_sha` 한 값 · `argv_sha256` 재계산 · 가족 안 `model` 한 종류.
- **V3 D 이후 정보 0** — `default_rng([20261004, 85])` 20행: **sha256(`input_text`) = `input_sha256`** ∧ 저장 텍스트의 모든 날짜 ≤ D · DB 재렌더(같은 컷오프)와 불일치 = **드리프트율 인쇄**(늦은 수정·삭제) · 검색 팔 20행(`[20261004, 89]`) `sources` 날짜 ≤ D · 누락 매칭 수기 재현.
- **V4 손계산 12로트** — 첫 로트 6 + 대조 6(`[20261004, 86]` · 팔 층화): 원시 OHLC 로 시가·qty·청산일·청산가·ret_pct.
- **V5 봉인** — 개봉-1 보고서에 δ·p·팔별 평균·연관 0 · `ledger_sha256.txt` 전 줄 = DB 재계산 · `robotrader` 역할로 봉인 표 SELECT 가 거부됨.
- **V6 git 순서** — 동결 < 코드 커밋 < 첫 행 < 개봉-1 < 개봉-2.
- **V7 반복·위치·비대칭** — 반복 일치율(점수 일치 · |Δ| ≤ 1 · 태그·위험 집합) · `batch_pos` 별 · R3~R5 수기 · Holm 수기 · 가짜 거부율.

## 12. 비용 상한 🔒

- 구현 = **executor 1 + verifier 1 · 토큰 합 ≤ 50만** · 구현 중 CLI ≤ 10회(가상 입력).
- 매일 = **구독 사용량만** · 본체 14~19 + 검색 팔 11~15(최대 30) ≈ **25~34호출/일**(최대 50) · OpenDART ≤ 60 · 벽시계 본체 ≤ 30분 · 검색 팔 ≤ 28분(08:30~08:58) · 시운전 3일 실측으로 EOD 갱신.

## 13. 금지 🔒

1. **개봉-2 전 누구도(관리자 포함)** §4 봉인 대상(`shadow.output_json`·`batch.raw_result`·`rep`·`search` 출력·`sources` 원문·런너 로그의 모델 출력)을 행 단위·값별 집계로 조회하지 않는다 — 허용 = 집계 뷰(행수/일 · status · 지연 · cost · 한도 오류 · 입력 커버리지 · model/cli_version/exe 해시 · 5점 비율은 개봉-1 에서만) · **검색 팔 (ㄱ)(ㄷ) 매일 · (ㄴ) 누적은 개봉-1 에서만**(점수 «값»이 아닌 집계 · 종목별 점수·짝별 차이는 금지).
2. EOD 보고서·텔레그램은 1 의 허용 집계만.
3. 첫 실행 뒤 프롬프트·스키마·모델·CLI(버전·exe·플래그)·채점 조건·입력 규칙 변경 = **새 가족**(사다리 3단계 밖은 개정문 + 사장님) · 섞기·풀링 금지.
4. 결과를 3전략 룰 변경·라이브 배선 근거로 인용 · 봇에서 읽기 · API 키 경로 · **본체**의 웹 도구 · `--fallback-model` · 전역 CLI 호출.
5. `rcept_no` 앞 8자리 날짜 · D 이후 입력 · 뉴스 점수 열 입력 · 라이브 트리 실행 · 더러운 워크트리 실행.
6. 개봉 뒤 T1~T3 정의·절단·에피소드·m=3·0.4%p·2%p·0.13·시드·라벨·사다리·채점 조건 변경 · 「판별 보류」를 「없음」으로 · 중간 언어.

## 14. 확인 문항 (답을 동결 커밋 메시지에 적는다)

- ✅ 답변됨: **Q1** 모델 `claude-opus-5-5`(사다리 F2 = `claude-sonnet-5` · F3·S1 = opus) · **Q2** T 16:10 · **Q5** 「850개 전부」→ 전 종목 규칙 · **Q7** 순환 20거래일(관리자).
- **Q4 ① 「자기주식취득 있음(+)」 힌트 주입?** — 기본 **아니오**(순진 유지 · 보조 T4 가 «넘어서는가»를 잰다).
- **Q6 시운전 3일 뒤 사다리 기준** — 한도 오류 (가) 1회라도 (나) **하루 2회 이상 또는 이틀 연속**(관리자 권고 · 기본) (다) 3회 이상 · 429/529 는 세지 않음.
- **Q8 검색 팔 비율** — (가) **5%**(기본 · 5~15호출) (나) 10%(10~30호출 · 한도 부담 큼).
- **Q9 계정 extra usage(추가 사용량 과금) 설정이 꺼져 있는지 사장님 확인** — 「추가 요금 없음」의 전제 · 켜져 있으면 한도를 넘는 사용이 과금될 수 있다 [추정].
- **Q10 DB 전용 역할·스키마 생성 승인** — `llm_shadow` 스키마 · `llm_shadow_writer` 역할 · `robotrader` 에 집계 뷰만 GRANT(부록 C · postgres 권한 필요 · 사장님 확인 뒤 실행).

## 부록 A. 프롬프트 v1 🔒 (펜스 안 본문이 해시 대상)

**A.1 시스템 프롬프트** (`--system-prompt`)
```
너는 한국 상장주식의 «재료(촉매)»와 «위험»을 분류하는 분석가다. 다음 규칙을 반드시 지킨다.
1) 사용자가 준 입력만 근거로 판단한다. 입력은 기준일 D 와 그 이전 날짜의 자료뿐이다. D 이후의 사건·주가·뉴스를 알고 있더라도 절대 쓰지 않는다. 입력에 없는 사실을 지어내지 않는다.
2) 도구·검색·외부 자료를 쓰지 않는다.
3) 종목마다 따로 판단한다. 같은 요청의 다른 종목과 비교해서 점수를 매기지 않는다. 입력에 있는 모든 종목을 code 로 구분해 items 에 하나씩 담는다.
4) catalyst_tags 는 아래 사전의 값만 쓴다(여러 개 가능). 재료가 하나도 없으면 ["없음"] 하나만 쓴다. "없음"은 다른 값과 함께 쓰지 않는다.
5) risk_flags 는 아래 사전의 값만 쓴다(여러 개 가능). 위험이 없으면 빈 배열 [] 을 쓴다.
6) score 는 D 다음 거래일 시가에 사서 약 2주~2개월 보유한다고 할 때 입력의 재료·위험만 보고 매긴 매력도다. 0~10 정수. 5 = 재료도 위험도 없음(또는 서로 상쇄). 10 = 매우 강한 긍정 재료이고 위험 없음. 0 = 매우 강한 위험.
7) 가격·거래량·차트 모멘텀으로 점수를 매기지 않는다. 시가총액·수익률은 참고일 뿐이다.
8) rationale 은 한국어 200자 이내로, 판단 근거가 된 입력 항목(날짜와 제목)을 짚는다.
9) 출력은 주어진 JSON 스키마에 맞는 객체 하나뿐이다.
[catalyst_tags 사전 — 재료 유형 · 방향 무관]
유상증자: 유상증자 또는 유무상증자 결정 공시(제3자배정 포함 · 무상증자만인 공시와 발행가 확정·청약 결과 같은 후속 절차는 제외하고 기타로)
CB/BW/EB: 전환사채·신주인수권부사채·교환사채 발행 결정
자기주식취득: 자기주식 취득 결정 또는 취득 신탁계약 체결(처분·소각은 제외)
공급계약: 단일판매·공급계약 체결 공시(해지는 제외)
최대주주변경: 최대주주 변경 또는 그것을 수반하는 주식 양수도·경영권 계약
잠정실적: 영업(잠정)실적 공정공시 또는 매출액·손익구조 30%(대규모법인 15%) 이상 변동 공시
소송·횡령: 소송 등의 제기·신청 또는 횡령·배임 혐의 발생·사실 확인
실적개선: 공시·기사가 전하는 매출·이익 증가, 흑자 전환, 전망 상향
수주: 공급계약 공시 밖에서 기사로 확인되는 수주·납품·계약 소식
신사업: 신규 사업·제품·인허가·기술이전·인수합병 같은 사업 확장 소식
기타: 위에 없는 재료(정책 수혜·테마 편입·무상증자 등) — rationale 에 무엇인지 적는다
없음: 재료 없음(단독으로만)
[risk_flags 사전 — 하방 위험]
유상증자: 지분 희석을 부르는 유상증자 결정
CB/BW: 전환사채·신주인수권부사채·교환사채 발행, 전환가액 하향 조정, 대량 전환 청구
소송: 소송 제기, 횡령·배임, 경영권 분쟁
최대주주변경: 최대주주·경영권 변경, 담보 주식 반대매매 우려
감사의견: 감사의견 비적정(한정·부적정·의견거절), 감사보고서 제출 지연, 계속기업 불확실성
관리종목: 관리종목·투자주의환기종목 지정, 거래정지, 상장폐지 사유 발생, 불성실공시법인 지정
기타: 그 밖의 뚜렷한 하방 위험(대규모 손실·자본잠식 등) — rationale 에 적는다
```
**A.2 사용자 메시지 틀** (stdin · 머리 1회 + 종목 블록 반복 · 값 없으면 `-` · 목록 없으면 `(없음)` · 줄 = `- MM-DD 제목` / `- MM-DD [출처] 제목`)
```
기준일 D: {D} (D 다음 거래일 {T} 시가 진입을 가정한다 · D 이후 정보 사용 금지)
아래 {k}개 종목을 각각 따로 판단해 items 에 종목마다 하나씩 담아라.
=== {i}/{k} {name} ({code}) · {market} · 시가총액 {mcap_eok}억원 · 최근 20거래일 수익률 {r20}
재무 (결산월 {stac_yymm}): 매출액증가율 {sales_growth}% · 영업이익증가율 {oi_growth}% · 순이익증가율 {ni_growth}% · ROE {roe}% · 부채비율 {liab}% · 유보율 {reserve}% · EPS {eps}원
DART 공시 제목 (최근 10거래일 {d10}~{D} · 최신순 · 최대 12건 · 전체 {n_dart_all}건):
{dart_lines}
기사 제목 (최근 5거래일 {d5}~{D} · 최신순 · 최대 8건 · 전체 {n_press_all}건):
{press_lines}
```
**A.3 JSON 스키마** (`--json-schema`)
```
{"type":"object","additionalProperties":false,"required":["items"],"properties":{"items":{"type":"array","minItems":1,"maxItems":20,"items":{"type":"object","additionalProperties":false,"required":["code","catalyst_tags","risk_flags","score","rationale"],"properties":{"code":{"type":"string","pattern":"^[0-9][0-9A-Z]{5}$"},"catalyst_tags":{"type":"array","minItems":1,"uniqueItems":true,"items":{"type":"string","enum":["유상증자","CB/BW/EB","자기주식취득","공급계약","최대주주변경","잠정실적","소송·횡령","실적개선","수주","신사업","기타","없음"]}},"risk_flags":{"type":"array","uniqueItems":true,"items":{"type":"string","enum":["유상증자","CB/BW","소송","최대주주변경","감사의견","관리종목","기타"]}},"score":{"type":"integer","minimum":0,"maximum":10},"rationale":{"type":"string","maxLength":200}}}}}}
```
**A.4 본체 명령** — `[<고정 exe>, "-p", "--model", "<가족 모델>", "--effort", "medium", "--safe-mode", "--tools", "", "--no-session-persistence", "--output-format", "json", "--json-schema", <A.3>, "--system-prompt", <A.1>]` · stdin = A.2 렌더 · `--effort` 는 help 에 있다([문서] `low|medium|high|xhigh|max`) · 실호출은 미시험 · `--bare` 금지(API 키 전용).
**A.5 검색 팔 규칙 2) 대체문** (A.1 의 `2) 도구·검색·외부 자료를 쓰지 않는다.` 한 줄을 바꾼다)
```
2) 웹 검색·웹 페이지 도구를 써도 된다. 검색으로 찾아 본 기사·공시는 제목·출처·날짜(YYYY-MM-DD)를 sources 에 전부 적는다. 날짜가 기준일 D 보다 늦은 자료는 판단에 쓰지 말고 excluded_after_D 에 적는다. 날짜를 알 수 없는 자료는 판단에 쓰지 않는다.
```
**A.6 검색 팔 스키마 추가분** (A.3 의 `items.items` 객체를 최상위로 쓰고 `properties` 에 아래 둘을 더하며 `required` 에 두 이름을 더한다)
```
{"sources":{"type":"array","maxItems":30,"items":{"type":"object","additionalProperties":false,"required":["title","source","date"],"properties":{"title":{"type":"string"},"source":{"type":"string"},"date":{"type":"string","pattern":"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},"url":{"type":"string"}}}},"excluded_after_D":{"type":"array","maxItems":30,"items":{"type":"object","additionalProperties":false,"required":["title","date"],"properties":{"title":{"type":"string"},"date":{"type":"string","pattern":"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}}}}}
```
**A.7 검색 팔 명령** — A.4 와 같되 `"--tools", "WebSearch,WebFetch"` · `--json-schema` = A.6 적용 스키마 · `--system-prompt` = A.1(규칙 2 → A.5) · stdin = A.2 1종목(둘째 줄 생략) · ⚠️ `WebSearch` 이름·권한 미시험(§5-9) · `prompt_sha256` = sha256(A.1 + A.2 + A.3 + A.5 + A.6 · "\n" 연결).

## 부록 B. CLI 실측 (v0.1 · 2026-09-26 · 워크트리 · 세션 변수 제거 · API 키 없음 · 3회)

- ① `--model sonnet --output-format json`: `PONG` · `modelUsage` 키 `claude-sonnet-5` · 입력 39,816 + 15,540(기본 에이전트 문맥) · $0.162426 · 7.5초 ② `--model claude-sonnet-5 --safe-mode --tools "" --no-session-persistence --system-prompt …`: 정식 이름 수용 · 입력 1,053 · $0.004266 · 4.2초 ③ `--model claude-opus-5-5` + ② + `--json-schema`: `structured_output` 정상 · `num_turns` 2 · `stop_reason` tool_use · 입력 1,594 · $0.0144 · 4.1초.
- 최상위 키: `type`·`subtype`·`is_error`·`api_error_status`·`result`·`structured_output`·`stop_reason`·`num_turns`·`duration_ms`·`total_cost_usd`·`usage`(`server_tool_use.web_search_requests`·`web_fetch_requests`)·`modelUsage`·`session_id` 등 · 모델은 `modelUsage` 키·`canonicalModel` 에만 · 한국어 UTF-8 정상 · CLI 2.1.283(전역 · 09-26 18:04:58 교체본 · `package.json` version 2.1.283 [실측]). **미시험**: stdin · 배열 스키마 20항목 · 묶음 지연 · 한도 오류 JSON · `--effort` 실호출 · WebSearch.

## 부록 C. DB 역할 · 스키마 초안 🔒 (Q10 승인 뒤 postgres 로 실행 · 열 = §4)

```sql
CREATE ROLE llm_shadow_writer LOGIN PASSWORD '<key.ini 별도 항목 · 문서에 쓰지 않음>';
CREATE SCHEMA llm_shadow AUTHORIZATION llm_shadow_writer;
-- 표(모두 llm_shadow 소유 · PK 는 §4): shadow · plan · batch · rep · search · search_daily_agg((ㄱ)(ㄷ) 일일 집계)  (DDL 본문 = 구현 코드 · 템플릿 db/repositories/sector_news.py:12)
REVOKE ALL ON SCHEMA llm_shadow FROM PUBLIC;
CREATE VIEW llm_shadow.v_daily_counts AS
  SELECT family, scan_date, trigger, status, carried, count(*) AS n, avg(latency_ms) AS latency_ms
  FROM llm_shadow.shadow GROUP BY 1,2,3,4,5;                         -- 점수·태그·입력·출력 열 없음
CREATE VIEW llm_shadow.v_batch_health AS
  SELECT family, scan_date, kind, count(*) AS calls, sum((is_error)::int) AS errors,
         count(*) FILTER (WHERE api_error_status IN (429, 529)) AS overload, sum(cost_usd) AS cost_usd
  FROM llm_shadow.batch GROUP BY 1,2,3;
CREATE VIEW llm_shadow.v_search_daily AS                            -- (ㄱ)(ㄷ) 만 · (ㄴ) 는 개봉-1 스크립트가 계산
  SELECT scan_date, n_sources_le_d, n_missing_disc, n_missing_press, n_db_unlinked, n_excluded_after_d, n_rule_violation
  FROM llm_shadow.search_daily_agg;
GRANT USAGE ON SCHEMA llm_shadow TO robotrader;
GRANT SELECT ON llm_shadow.v_daily_counts, llm_shadow.v_batch_health, llm_shadow.v_search_daily TO robotrader;
```
- 시드 표(`default_rng([20261004, x, …])`): 81 대조 · 82 본체 묶음 섞기 · 83 반복 선택 · 84 개봉-2 가짜 · 85 V3 · 86 V4 · 87 (A) 넘침 채움 · 88 검색 팔 표본 · 89 V3 검색 팔 · **90 반복 묶음 섞기 · 91 재시도 묶음 순서 · 92 검색 팔 호출 순서 · 93 개봉-1 가짜 · 94 보조 가짜**(v0.5 지정) · 조각 = sha256 키(§3-2 · 난수 아님).
