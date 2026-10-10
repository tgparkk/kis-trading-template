# 사전등록 — daytrading 수급 4종 07:52 봉인 기록(B · `dtflow_shadow`): 꼬리 20% 후보는 나쁜가

**상태: 초안(동결 전)**

- 작성 2026-10-10(토) · 초안 = 가상매매 세션 직원(계획 Task 9 Step 1) · 다음 = critic 1패스 → 🔒 사장님 동결(A 사전등록 · DDL 적용 · 작업 등록과 **한 번에** · 계획 Task 9 Step 3).
- 규범: 스펙 `docs/superpowers/specs/2026-10-10-daytrading-filter-layer-design.md`(main `75326bc`) §0·§4·§5·§7 · 계획 `docs/superpowers/plans/2026-10-10-daytrading-filter-B-flow-shadow.md`(main `c859e91`) · SDD 원장 `.superpowers/sdd/2026-10-10-daytrading-filter-B-flow-shadow/progress.md` 의 `Ruling:` 줄(구현 중 결정).
- 값의 출처 = 코드: 패키지 `RoboTrader_template/backtest/concept_axes/dtflow_shadow/` · 러너 `RoboTrader_template/scripts/dtflow_shadow_recorder.py` · 기준 커밋 `394eeb6`(브랜치 `research/dt-flow-shadow`).
- 🔴 이 문서의 값은 위 커밋의 코드에서 옮겼다. **동결 커밋에서 코드와 이 문서가 한 곳이라도 다르면 동결하지 않는다.**
- 꼬리표(값 옆 출처): `(settings.py: 이름)` · `(runner: 이름)` = 러너 파일 · `(코드: 파일)` · `(ddl.sql)` · `(register_tasks.ps1)` · `(spec §x)` · `(plan: …)` · `(Ruling: …)` = SDD 원장 · **`(초안 해석)`** = 스펙이 정하지 않아 이 초안이 고른 것(critic·사장님 확인 대상).
- 등재 예정 코드 **DF2** · 주 검정 **4**(Holm 가족) — 등재 문안 §0-4.

---

## §0. 결정·범위

### 0-1. 사장님 결정 (말 그대로 · spec §0 · 2026-10-10)

| 질문 | 답 |
|---|---|
| (발단) | 「daytrading 에 대해 이야기하죠. 퀀트와 뉴스데이터 활용이 필요하다고 생각합니다.」 |
| 어디에 쓰나 | 「거르기 — 나쁜 후보 빼기」 |
| 근거 수준 | 「과거 검정 통과 후 적용」 |
| 재료 | 「공시 악재 — 과거 확인 검정」 + 「수급·언론 뉴스 — 오늘부터 기록」 → 뒤에 「B 는 수급 4종만」(뉴스는 기존 LLM shadow·TN1·테마 층에 맡김) |
| 검정 구간 | 「뭐가 좋을지 모르겠음」 → 쉬운 설명 뒤 「① 으로 진행」(아무도 안 본 2021~2024-03) |
| 기록 방식 | 「DB 봉인 이 어떤 의미인가요?」 → 「뭐가 더 확실히 조사할수 있는건가요?」 → 「② DB 봉인으로」 |
| 과거 시총 없음 | 「ⓐ 시총 조건 빼고 안 본 구간 검정」 |
| 설계 §1·§2 | 「좋아요 — 다음 절로」 |
| (중간) | 「근데 아마 문서로 다음에 할일들을 적어놓은게 있는데 문서한번보고 진행해줘요」 → `NEXT_SESSION.md`·10-17 안건 확인 |
| 09-24 결정과 충돌 | 「그렇게 진행」 = 09-24 「후보 층 재시도 안 함 · 더 찾지 않음」을 **이 건에 한해 면제** · B 는 수급 4종만 |
| 설계 §3·§4 | 「고수랑 논의하고 작성하세요」 → 전문가 패널 3인(spec §8) |
| A 수정안 | 「수정안으로」(돌파일 당일 공시 · 경영권분쟁 제외 · 도구 교체 · 시총 대리 · 정지 처리) |
| B 시작 시점 | 「늦출 필요 없다고 생각하는데 , 의견좀요」 → 관리자 권고 변경 → 「그렇게 진행」(지금 준비 · 점검 통과 뒤 봉인 ≈10-26~28) |
| 범위 밖 | 「10-19 전에 점검」 = 보유 중 권리락 «가짜 손절» 조사(spec §9) |

### 0-2. 09-24 결정 면제 (말 그대로 · spec §5)

> **면제**: 09-24 「후보 층 재시도 안 함 · 현행 유지 · 더 찾지 않음」을 **daytrading A·B 에 한해** 면제(사장님 10-10 「그렇게 진행」) · 테마 층 면제 선례대로 `backtest/concept_axes/REGISTRY.md` 등재.

- 면제는 «이 건»뿐이다. B 의 재료는 수급 4종뿐이다(뉴스·가격 퀀트 특징·재무 부실은 범위 밖 · spec §1).

### 0-3. 이 문서의 범위 — 네 문장

1. 이 문서는 **기록 규칙**(무엇을 언제 어떻게 봉인하나 · §2~§4)과 **판정 규칙**(봉인 120(250)거래일 뒤 1회 · §5)을 함께 동결한다. 판정 코드는 아직 없다 — 개봉 도구는 별도 계획이고 §5 를 바꾸지 않고 구현한다(plan 「스펙과 다른 점」 1).
2. 시험 단계(§4) 값은 판정에 쓰지 않는다(spec §4-1).
3. 🔴 라이브 봇 코드 0줄 · DB 쓰기 = 새 스키마 `dtflow_shadow` 만 · KIS = 조회 TR 4개만 · 토큰 발급 0(spec §1·§6 · plan Global Constraints).
4. 기대 크기 = «보험»이다(spec §1). 이 설계는 「없음」을 선언할 수 없다(spec §7).

### 0-4. 등재 문안 (동결 «뒤» REGISTRY 에 붙인다 · 이 초안은 REGISTRY 를 건드리지 않는다)

`| **DF2** | [PREREG](dtflow_shadow/PREREG.md) | daytrading_3methods_breakout | 수급 4종 꼬리 20% | ⚪ 탐색 열 | **4** | ✅ 동결 <날짜> · <SHA> |` (plan: Task 9 Step 5)

- 총계는 «한 push 연속 마지막 커밋»에서 갱신한다(REGISTRY 규칙 3). DF1·TN1·SR1·테마 층과 충돌하면 나중에 머지되는 쪽이 다시 센다(spec §5).

---

## §1. 가설 (방향 고정 · 단측)

| # | 특징(§3-1) | 나쁜 꼬리 | H₁ | 비고 |
|---|---|---|---|---|
| H1 | ① 기관 순매수 ÷ 거래대금 | 날짜 안 **하위 20%** | 꼬리의 net 수익 < 나머지 | 외국인은 ② 와 상관 0.968 이라 뺐다(§7 · spec §8) |
| H2 | ② 프로그램 순매수 ÷ 거래대금 | 날짜 안 **하위 20%** | 같음 | 외국인 대용(spec §4-3) |
| H3 | ③ 공매도 거래량 비중 | 날짜 안 **상위 20%** | 같음 | 🔴 방향 확신 낮음(spec §4-3) |
| H4 | ④ 신용잔고율(D−k) | 날짜 안 **상위 20%** | 같음 | 위험 구간(≥7%) 표본 희소 예상(spec §4-3) |

- 효과 `δ_j` = (특징 j 꼬리 표본의 평균 net 수익) − (나머지 표본의 평균 net 수익) · 단위 %p. 꼬리·나머지는 §5-1 표본 안에서 날짜마다 나눈다.
- `H₀: δ_j ≥ 0` · `H₁: δ_j < 0`(spec §4-5).
- 네 가설은 한 Holm 가족이다(m=4 · spec §4-5·§5). 탐색 열(§3-3)은 가족 밖이고 인쇄만 한다.

---

## §2. 기록 규칙

### 2-1. 시각

| 항목 | 값 | 출처 |
|---|---|---|
| 기록 작업 | 월~금 **07:52** · StartWhenAvailable · 겹치면 새 실행 무시(IgnoreNew) · 실행 제한 30분 | (register_tasks.ps1) (spec §4-2) |
| 시작 하한 | `--record` 가 **07:50 전**이면 거부(행 없음 · exit 2) | (settings.py: START_NOT_BEFORE) |
| 시작 상한 | 시작 시각 **≥ 08:38** = `missed_host` 행 · 후보 행 없음 | (settings.py: REFUSE_AFTER) (spec §4-2) |
| 봉인 마감 | 조회가 끝난 시각 **> 08:40** = `late`(행은 쓰되 주 검정 제외) | (settings.py: SEAL_DEADLINE) (spec §4-2·§4-4) |
| 스냅샷 대조 | 월~금 **09:05** · **09:03 전** 실행은 `too_early`(행 없음 · exit 2) | (register_tasks.ps1) (settings.py: SNAPSHOT_NOT_BEFORE) (Ruling: Task 7 I4) |

- 실행 위치 = 동결 커밋을 «detached» 로 꺼낸 운영 워크트리 `D:\tmp\kis-wt-dtflow-run` · 인터프리터 = 라이브 venv 의 python 실행 파일(작업 폴더는 운영 워크트리) (register_tasks.ps1) (plan Global Constraints).
- 홈 = `%LOCALAPPDATA%/kis-dtflow-shadow`(env `KIS_DTFLOW_SHADOW_HOME`) — `frozen.json` · `frozen_history.jsonl` · `runner.lock` · `logs/` (settings.py: home_dir, frozen_path, lock_path, log_dir).

### 2-2. 가드 (매 실행 · 순서대로 · 하나라도 걸리면 DB 에 아무것도 쓰지 않는다)

1. 러너가 라이브 트리 `D:/GIT/kis-trading-template` 아래에 있으면 거부(settings.py: LIVE_TREE) (spec §4-2).
2. `frozen.json` 을 읽는다 — 없음·깨진 JSON·필드 형식 이상이면 거부(Ruling: Final I3).
3. `rule_v` = `v1`(settings.py: RULE_V) · `credit_lag_k` = 코드의 값(settings.py: CREDIT_LAG_K) · HEAD = 동결 `code_sha` · 작업 트리 clean · detached(브랜치 위면 거부) (코드: guard.check_runtime).
4. 홈이 LLM·태쏘 shadow 홈과 같으면 거부(settings.py: other_homes) (spec §4-4).
5. 라이브 원본 **7파일**의 목록이 동결 목록과 같고(Ruling: Task 1 Important 1), 파일마다 sha256(CRLF→LF 정규화 · DOSSIER_B §0-5)이 동결 값과 같아야 한다(settings.py: LIVE_SOURCES) (spec §4-2):
   - `strategies/daytrading_3methods_breakout/screener.py`
   - `strategies/_rule_screener_base.py`
   - `strategies/books/daytrading_3methods/rules.py`
   - `db/quant_daily_reader.py`
   - `utils/data_sanity.py`
   - `api/kis_market_api.py`
   - `api/kis_auth.py`
   - 스펙은 스크리너 원본 5개 + «KIS 엔드포인트·헤더 원본 sha 고정»을 요구한다(spec §4-2). 코드는 둘을 합친 7개다(`api/kis_auth.py` = 헤더·토큰 파일 형식의 원본).
- 거부 = 경보 `guard_refused GuardError/<reason>` + 일자 로그 + exit 2 · DB 행 없음 ⇒ 그날은 결측일(§2-8). reason 코드 = `live_tree` · `home_collision` · `git_failed` · `frozen_missing` · `frozen_corrupt` · `dirty` · `rule_v` · `credit_lag_k` · `head_mismatch` · `not_detached` · `source_list` · `source_sha` · `source_unreadable`(코드: guard.py).
- 가드 뒤 실행 조건: 휴장(§2-4) = exit 0 · 행 없음 / `--record` 07:50 전 = exit 2 · 행 없음 / 잠금 사용 중 = exit 3 · 행 없음(runner: main).

### 2-3. 하루 순서 (`--record` · runner: _run_record)

1. T(오늘) 가 거래일인지 본다 → D = T 의 직전 거래일(§2-4).
2. 그 D 에 record run 행이 이미 있으면(단계·상태 무관) **아무것도 쓰지 않고** 경보 `already_recorded` + exit 2(Ruling: Final I1 · spec §4-4 「나중에 채우지 않음」).
3. 단계를 정한다(시험/봉인 · §4-2).
4. 시작 시각 ≥ 08:38 → `missed_host` 행.
5. D 가격 완결 확인(§2-5) → 실패면 `universe_stale` 또는 `missed_sweep` 행.
6. 후보 계산(§2-5).
7. 토큰·key.ini 읽기(§2-6) → 실패면 `missed_token` 행.
8. 후보마다 KIS 4 TR 조회(§2-6) → 응답 원문 · `body_sha256` · `fetched_at`.
9. 특징 계산(§3).
10. 조회가 끝난 시각 > 08:40 이면 `late`.
11. 후보 행 + 원문 행 + run 행을 **한 트랜잭션**으로 쓴다(`ON CONFLICT DO NOTHING` · 한 행이라도 충돌이면 전부 롤백하고 예외) (코드: store.PgStore._tx) (spec §4-4).
12. CSV 원장을 내보낸다(§2-9).
13. vintage 2(§2-7 · 판정 미사용).

- `--check-snapshot`(09:05): D 를 같은 방법으로 정한다 → 그 D 의 기록기 후보와 `screener_snapshots` 를 대조한다(§2-5) → snapshot_check run 행 1개(§2-8). 단계 = 봉인 run 행이 하나라도 있으면 봉인 표, 아니면 시험 표(Ruling: Final M1).

### 2-4. D 와 달력

- 거래일 = 평일 ∧ `utils.korean_holidays.is_holiday` 가 아님 ∧ 12-31 아님(라이브 봇과 같은 달력 모듈) (runner: _is_trading_day) (Ruling: Final I1).
- D = T 의 직전 거래일(최대 31일 거슬러 봄) · D′ = D 의 직전 거래일 · 신용 시차·전환 창 달력 = D 를 포함한 최근 40거래일(runner: _prev_day, _cal, CAL_DAYS).
- 🔴 KOSPI 의사티커(`daily_prices` 적재 상태)로 D 를 정하지 않는다 — 늦게 적재된 날 엉뚱한 D 를 막기 위해서다(Ruling: Final I1). (DOSSIER_B §2-4 는 KOSPI 교차 확인을 권했으나 쓰지 않는다.)
- 한계: KIS 휴장 캐시(`holiday_kis_cache.json`)는 «현재 작업 폴더» 기준으로 읽힌다. 작업 스케줄러의 작업 폴더 = 운영 워크트리 루트라 캐시가 안 읽히고, 정적 달력(holidays 라이브러리 + 수동 특수 휴일)만 쓴다(DOSSIER_B §1-7 · SDD Final residual). 정적 달력에 없는 임시 휴장은 §6-5 처럼 status 로 드러난다.

### 2-5. 후보 계산 = 스크리너 SQL·룰 복제 (라이브 import 0 · spec §4-2)

| 항목 | 값 | 출처 |
|---|---|---|
| D 가격 완결 | (D 의 `market_cap IS NOT NULL` 행 수) ÷ (D′ 의 같은 행 수) **≥ 0.98** ∧ 유니버스 날짜 = D · 실패 시 유니버스 날짜 ≠ D 면 `universe_stale`, 같으면 `missed_sweep` | (settings.py: D_ROWS_RATIO_MIN) (코드: candidates.d_complete) |
| 유니버스 | `daily_prices` 에서 `max(date) ≤ D ∧ market_cap IS NOT NULL` 인 날짜의 행 | (코드: candidates.UNIVERSE_SQL) |
| 1차 조건 | 0 < 시총 < **5,000억**(결측·0 제외) ∧ 거래대금(`close × volume * COALESCE(adj_factor, 1)`) ≥ **10억** | (settings.py: MAX_MCAP, MIN_TV) |
| 일봉 | D 이하 최근 **60봉** · 거래량 = SQL 한 줄 안의 `volume * COALESCE(adj_factor, 1)` | (settings.py: LOOKBACK_BARS) |
| 불가능봉 | 60봉 안 종가 수익률 **< −35%** 가 하나라도 있으면 제외 | (settings.py: IMPOSSIBLE_RET) |
| 룰 | 봉 ≥ 17 ∧ 종가 ≥ 직전 **15봉** 고가 최대 ∧ 직전 **20봉** 평균 거래량 > 0 ∧ 마지막 거래량 ≥ 평균 × **2.0** ∧ 종가 > 시가 ∧ 종가 > 0 | (settings.py: HIGH_WINDOW, VOL_LOOKBACK, VOL_MULT) |
| 점수 | 마지막 거래량 ÷ 직전 20봉 평균(0 이면 1) | (코드: candidates.match) |
| 순위 | 점수 내림차순 · 안정 정렬(동점 = 유니버스 SQL 순서) | (코드: candidates.rank) |
| 스냅샷 대조 | `screener_snapshots` · strategy = `daytrading_3methods_breakout` · params_hash = `46594669e8b6af417143556ea3c0066d2ccc9984` · 일치 = 종목 집합 같음 ∧ 순위 같음 ∧ max \|Δscore\| **< 1e-9** | (settings.py: FOLDER, PARAMS_HASH) (코드: candidates.compare) (spec §4-1(a)) |

- 🔴 가격에 `adj_factor` 를 곱하지 않는다 · 거래량 조정은 SQL 한 줄 안에서만(레포 가드 · plan Global Constraints).
- 스펙의 «표지 행 updated_at» 검사(spec §4-2 ②)는 구현하지 않았다 — §4-4 에서 «뺀 것»으로 선언한다.

### 2-6. KIS 호출

| 종류 | TR | 경로 | 쿼리 파라미터 | 응답 행 | D 행 |
|---|---|---|---|---|---|
| investor | `FHKST01010900` | `/uapi/domestic-stock/v1/quotations/inquire-investor` | `FID_COND_MRKT_DIV_CODE=J` · `FID_INPUT_ISCD=종목` | `output` | `stck_bsop_date == D` |
| program | `FHPPG04650201` | `/uapi/domestic-stock/v1/quotations/program-trade-by-stock-daily` | 위 + `FID_INPUT_DATE_1=T` | `output` | `stck_bsop_date == D` |
| short | `FHPST04830000` | `/uapi/domestic-stock/v1/quotations/daily-short-sale` | 위 2개 + `FID_INPUT_DATE_1=D−20일(달력일)` · `FID_INPUT_DATE_2=D` | `output2` | `stck_bsop_date == D` |
| credit | `FHPST04760000` | `/uapi/domestic-stock/v1/quotations/daily-credit-balance` | `J` · `FID_COND_SCR_DIV_CODE=20476` · 종목 · `FID_INPUT_DATE_1=T` | `output` | `deal_date`(§3-1 ④) |

- 출처: (settings.py: TRS, KINDS, SHORT_SPAN_DAYS) (코드: kis.params_for, features.rows_of) (spec §4-2). 날짜 = `YYYYMMDD`. GET · 헤더 = `Content-Type: application/json` · `Accept: text/plain` · `charset: UTF-8` · `User-Agent: StockBot/1.0` · `authorization: Bearer <토큰>` · `appkey` · `appsecret` · `tr_id` · `custtype: P` · `tr_cont: ""`(코드: kis.Client._headers · 라이브 `api/kis_auth.py` 복제).
- 🔴 조회 TR 4개만 · 주문 TR 0(spec §4-2).
- **토큰 — 발급 0 · 읽기만**:
  - 라이브 페이퍼 봇 토큰 파일 `D:/GIT/kis-trading-template/RoboTrader_template/token_info.json`(env `KIS_DTFLOW_SHADOW_TOKEN`) (settings.py: token_path). 형식 = YAML 2줄 `token:` · `valid-date: YYYY-MM-DD HH:MM:SS`(KST) (DOSSIER_B §4).
  - `missed_token` 조건: 파일 없음 · 형식 이상 · 남은 시간 < **1,200초**(settings.py: TOKEN_MIN_LEFT_S) · 읽기 오류(OSError·UnicodeDecodeError — 07:40 봇이 파일을 다시 쓰는 중 포함) · key.ini 읽기 오류 · 조회 중 만료 응답(`EGW00123` 또는 msg1 「기간이 만료된 token」) (코드: kis.read_token, kis._expired) (runner: _run_record).
  - `/oauth2/tokenP` 호출 코드 없음 · 실전 인스턴스 토큰 `token_info_daytrading.json` 은 열지 않는다(plan Global Constraints · spec §4-2).
- key.ini: 라이브 `RoboTrader_template/config/key.ini` `[KIS]` 의 `KIS_BASE_URL`·`KIS_APP_KEY`·`KIS_APP_SECRET` 를 읽기만 한다 · 보간 없음(`interpolation=None`) · 값은 로그·경보에 쓰지 않는다(settings.py: key_ini_path) (Ruling: Final I6).
- 속도: 호출 간격 ≥ **0.10초**(settings.py: CALL_INTERVAL_S) · 타임아웃 **(5, 30)초**(settings.py: HTTP_TIMEOUT) · `EGW00201`(초당 건수 초과) = **1.5 × 2ⁿ초** 대기 뒤 재시도 최대 **3회**(settings.py: RETRY_BASE_S, RETRY_MAX).
- 응답 판정:
  - `rt_cd ≠ "0"` = 실패 1건(`n_fail`).
  - 조회 중 네트워크 예외 = 그날 `error`(error_text = 예외 형식 이름 · 받은 응답 버림 · 후보 행 0) (Ruling: Task 7 I1).
  - vintage 1 응답이 «전부» 실패 = 그날 `error`(`AllCallsFailed` · 후보 행 0) (Ruling: Task 7 I3).
  - 일부 실패 = 정상 기록 + 그 종목의 has_* = false(가용률에 드러남).
- 호출 수(추정): vintage 1 ≈ 후보 수 × 4(spec §4-2 ≈190) + vintage 2 ≈ 전날 후보 수 × 4 ⇒ 후보 27~52(DOSSIER_B §2-4 · §7-4)이면 하루 ≈220~420회.

### 2-7. 저장

- 표 6개(부록 A · 스키마 `dtflow_shadow` · settings.py: SCHEMA): 시험 `trial_candidates`·`trial_raw`·`trial_run` / 봉인 `candidates`·`raw`·`run` — 열이 같다(plan 「스펙과 다른 점」 2 · spec §4-1 「시험 표」).
- 후보 행(PK `rule_v, scan_date, stock_code`): 순위 · 점수 · 특징 4 · 탐색 열 · has_* · `late` · `code_sha` · `row_sha`.
- 원문 행(PK `rule_v, scan_date, stock_code, kind, vintage`): kind ∈ {investor, program, short, credit} · vintage 1 = 그날 아침 D 조회 · 2 = 다음 기록일 아침 재조회 · `fetched_at`(응답 받은 시각 · KST · ms) · `rt_cd` · `msg_cd` · `body`(jsonb) · `body_sha256`.
- run 행(PK `rule_v, scan_date, run_kind, run_at` · run_at 은 초 단위): 상태 · 후보 수 · 호출 수(재시도 포함) · `n_fail` · 가용률 4 · 스냅샷 대조 결과 · 유니버스 날짜 · D/D′ 행 수 · `rows_sha256` · 소요 ms · `code_sha` · `error_text`(예외 «형식 이름»만).
- 🔴 미도착 = NULL · 나중에 채우지 않는다 · vintage 2 로 vintage 1 의 NULL 을 메우지 않는다 · 놓친 날을 다른 날 다시 기록하지 않는다(already_recorded) (spec §4-4) (Ruling: Final I1).
- 🔴 `late` 행은 봉인 표에 남지만 주 검정에서 뺀다(spec §4-4).
- **vintage 2**(판정 미사용 · spec §4-2): 그날 기록이 커밋된 «뒤», 08:38 전이면, 직전 스캔일 D′ 후보(D′ 후보 행이 있는 단계의 표)에 대해 같은 4 TR 을 다시 받아 원문만 저장한다 — 별도 트랜잭션 · 실패해도 그날 기록 불변 · 로그만(runner: _vintage2). 용도 = «아침 값 = 최종값» 비율 인쇄. 그날 기록이 ok/late 로 커밋되지 않은 날은 vintage 2 도 없다.

### 2-8. 상태 어휘 · 하루 여러 행 규칙 · 결측일

**record 행 (`run_kind = record`)**

| status | 조건 | 후보·원문 행 | 경보 | 판정에서 |
|---|---|---|---|---|
| `ok` | 정상 · 조회 끝 ≤ 08:40 | 있음 | 없음 | 표본 후보(§5-1) |
| `late` | 조회 끝 > 08:40 | 있음(`late=true`) | `late` | 제외 · 인쇄만 |
| `missed_host` | 시작 ≥ 08:38 | 없음 | 있음 | 결측일 |
| `universe_stale` | 유니버스 날짜 ≠ D | 없음 | 있음 | 결측일 |
| `missed_sweep` | D/D′ 행 수 < 0.98 | 없음 | 있음 | 결측일 |
| `missed_token` | §2-6 토큰 조건 | 없음(조회 중 만료면 받은 응답도 버림) | 있음 | 결측일 |
| `error` | `NoPrevTradingDay` · 네트워크 예외 형식 이름 · `AllCallsFailed` · 그 밖 예외 형식 이름(최선노력 기록 · Ruling: Task 7 I2) | 없음 | 있음 | 결측일 |

**snapshot_check 행 (`run_kind = snapshot_check`)**

| status | 조건 |
|---|---|
| `ok` · `snapshot_match = true` | 일치(§2-5) |
| `ok` · `snapshot_match = false` | 불일치 — 경보 라벨 `snapshot_mismatch`(status 값이 아니다) |
| `no_record` | 그 D 의 기록기 후보 행도 ok record 행도 없음 |
| `no_snapshot` | 09:00 스냅샷이 0행(봇 미가동 · 후보 0 등) (Ruling: Final M1) |
| `error` | D 를 못 정함 · 예외 |

**행을 쓰지 않는 결과**

| 이름 | 조건 | 종료 |
|---|---|---|
| `already_recorded` | 그 D 에 record 행이 이미 있음(경보) | exit 2 (Ruling: Final I1) |
| `too_early` | `--check-snapshot` 09:03 전 | exit 2 (Ruling: Task 7 I4) |
| `guard_refused` | 가드 거부(경보 · §2-2) | exit 2 |
| (시작 시각 전) | `--record` 07:50 전 | exit 2 |
| (LockBusy) | 잠금 사용 중 | exit 3 |
| (휴장) | T 가 거래일 아님 | exit 0 |

- 스펙의 status `missed_flow`·`flow_absent` 는 두지 않았다(spec §4-4 와 다름). 조회 실패·D 행 없음은 «종목 단위»라 has_*·avail_*·`n_fail`·원문 `rt_cd` 로 남기고, 하루 전체 실패만 `error` 로 쓴다(Ruling: Task 7 I1·I3). `snapshot_mismatch` 는 경보 라벨이다.

**하루 여러 행 규칙**

1. **record**: 정상 경로는 D 당 record 행 1개다(already_recorded 가 두 번째 실행을 막는다). 2개 이상이 생기는 경우 = 커밋 «뒤» 단계(CSV 원장 내보내기 등) 예외로 `error` 행이 덧붙은 경우뿐이다(SDD Task 7 minor). 규칙: **후보 행과 같은 트랜잭션으로 커밋된 행**(status `ok`/`late` · `rows_sha256` 있음)이 그날의 정본이다. 뒤따른 `error` 행은 인쇄만 하고 정본을 바꾸지 않는다(봉인 행의 유효성은 §2-9 해시 재계산으로만 판단). 후보 행이 없는 날은 run_at 이 가장 이른 record 행이 정본이다(초안 해석).
2. **snapshot_check**: 09:05 작업 1회가 원칙이고 🔴 **수동 재실행 금지**. 그래도 2개 이상이면 run_at 이 가장 이른 행이 정본이다(초안 해석). ⚠️ 시험→봉인 자동 판정 코드(`phase.seal_ready`)는 «읽힌 ok 행 중 마지막 것»을 쓴다(SDD Task 6 minor). 재실행이 있었던 시험일이 전환 판정 10일 안에 들면, 전환 직후 관리자가 정본 규칙으로 다시 대조해 보고하고, 갈리면 사장님이 정한다(§9-4).
3. **결측일** = 봉인 단계 달력 거래일 중 정본 record 가 `ok`/`late` 가 아니거나 record 행이 아예 없는 날(가드 거부 · PC 가 종일 꺼짐 · 잠금 등). 건수·사유를 블라인드 점검과 개봉 때 인쇄한다. 나중에 채우지 않는다.

### 2-9. 해시 정의

- **`body_sha256`**(원문 행) = sha256(UTF-8(`json.dumps(body, ensure_ascii=False, sort_keys=True)`)) · body = KIS 응답 JSON 을 파싱한 dict(runner: _run_record, _vintage2).
- **`row_sha`**(후보 행마다) = sha256(UTF-8(「`열=값`」 줄들을 `\n` 으로 이은 문자열)) · 열 = 후보 열 25개에서 **`run_at`·`code_sha`·`row_sha` 를 뺀 22개를 이름순** · 값 표기 `cell()` = NULL→빈칸 · bool→`true`/`false` · date/datetime→ISO · float→`repr`(NaN→빈칸) · dict/list→JSON(sort_keys) · 그 밖→`str` (코드: store.row_sha, store.cell, store.HASH_EXCLUDE) (Ruling: Final I7).
- **`rows_sha256`**(record run 행) = sha256(CSV 바이트) · CSV = 머리줄(위 22열 · DDL 열 순서) + 행(`scan_date`, `stock_code` 순 정렬) · `csv.writer` · 줄끝 `\n` · UTF-8 · 후보 0 이면 머리줄만(코드: store.rows_sha256, store.to_csv) (Ruling: Final I7).
  - 22열 = `rule_v, scan_date, stock_code, rank, score, f1_orgn, f2_prog, f3_short, f4_credit, credit_deal_date, credit_lag, has_investor, has_program, has_short, has_credit, x_frgn, x_prsn, x_orgn5, x_loan_gvrt, x_ssts_amt_rlim, acml_tr_pbmn, late`.
  - 빼는 이유: `run_at`(실행 시각 · DB timestamptz 왕복 때 표기가 바뀜) · `code_sha`(코드 판 · 내용 아님) · `row_sha`(자기 자신). ⇒ DB 에서 다시 읽어도 같은 값이 나온다.
- **CSV 원장**: 커밋 뒤 `<archive>/<단계>/<D>/candidates.<YYYYmmddTHHMMSS>.csv`(후보 열 **25개 전부**) 를 쓰고, `<archive>/<단계>/ledger_sha256.txt` 에 `D · candidates · 행 수 · 파일 sha256 · 파일 이름 · 시각`(TAB) 한 줄을 덧붙인다 · archive = `D:/research-archive/dtflow_shadow`(env `KIS_DTFLOW_SHADOW_ARCHIVE`) (코드: store.export_ledger) (settings.py: archive_dir) (spec §4-4).
  - 🔴 이 «파일 sha» 는 열 집합이 달라 `rows_sha256` 과 같은 값이 아니다. 원문 행·run 행은 CSV 로 내보내지 않는다(DB 에만 있다).
- **개봉 때 검증**(초안 해석): ① DB 후보 행마다 `row_sha` 재계산 = 저장값 ② 날마다 `rows_sha256` 재계산 = 정본 run 행의 값 ③ CSV 원장 파일 sha = `ledger_sha256.txt` 값 ∧ CSV 의 22열 = DB 값 ④ 원문 행마다 `body_sha256` 재계산 = 저장값. 하나라도 어긋난 날 = 표본 제외 + 보고(§9-7).

### 2-10. DB 권한 모델 (ddl.sql · Ruling: Final I5)

- 소유 역할 `dtflow_shadow_owner` = **NOLOGIN**(비번 없음 · 접속 불가) · 스키마와 표 6개를 소유한다.
- 쓰기 역할 `dtflow_shadow_writer`(settings.py: WRITER_ROLE) = LOGIN · 비번 = 라이브 key.ini `[DTFLOW_SHADOW] db_password`(보간 없음 · 로그 금지 · Ruling: Final I6) · 권한 = 표 6개 **INSERT·SELECT 만**(UPDATE·DELETE·TRUNCATE·DROP·소유 없음 → 봉인 행을 이 역할로 바꾸거나 지울 수 없다) · `public.daily_prices`·`stock_info`·`screener_snapshots` SELECT · DB CONNECT · `public` USAGE.
- `robotrader` = 스키마 USAGE + 표 SELECT · PUBLIC = 스키마·표 권한 없음.
- 입력 읽기는 쓰기 역할이 아니라 **`robotrader` 읽기 전용 세션**으로 한다(runner: _open_inputs · `replayer.loader.dsn` · `set_session(readonly=True)`). 쓰기 역할의 `public` SELECT 권한은 spec §4-4 대로 두지만 지금 코드는 쓰지 않는다.
- 쓰기 DB 이름 = `config.constants.resolve_daily_source_db()`(resolver 경유 · 코드: store.connect_writer) · host·port = env `TIMESCALE_HOST`·`TIMESCALE_PORT`(기본 `127.0.0.1`·`5433`).
- DDL = 1회 실행 · retention·DROP·IF NOT EXISTS 없음(이미 있으면 멈춤) · 빈 비번이면 아무것도 만들지 않고 중단(부록 A).
- 🔴 한계: 슈퍼유저(`postgres`)는 여전히 봉인 행을 바꿀 수 있다. «바뀌지 않았다»의 증거는 §2-9 해시와 archive 의 CSV 원장이다.

### 2-11. dry-run (Ruling: Final I4 · Task 7 I5)

- `--dry-run` = **KIS 스텁**(모든 호출이 `rt_cd "0"` · `msg_cd "DRYRUN"` · 빈 출력 → 특징 전부 NULL) · 실 토큰·key.ini 읽기 0 · KIS 호출 0 · 메모리 저장(DB 쓰기 0) · 입력 DB 는 읽기 전용 · 경보는 보내지 않고 로그만(runner: _StubKis, _open_store).
- `--date`·`--no-guard`·`--home`·`--archive`·`--now HH:MM` 은 `--dry-run` 과 함께만 쓸 수 있다 · `--freeze --dry-run` 은 거부(runner: main).
- dry-run 결과는 어느 표에도 들어가지 않는다 ⇒ 전환·판정과 무관하다. 실 KIS 경로 확인은 Task 10 장 전 수동 `--record` 1회(시험 표)가 맡는다(plan Task 10 Step 4).

### 2-12. 경보·로그·종료 코드

- 텔레그램 = 라이브 key.ini `[TELEGRAM] token`·`chat_id` 읽기만 · 한 실행 1통(가드 거부는 즉시 1통) · 본문 = `[kis-dtflow-shadow] D=YYYY-MM-DD status=… n=…` 또는 `guard_refused GuardError/<reason>` · 예외는 «형식 이름»만(코드: alerts.py) (spec §4-4).
- 일자 로그 `<홈>/logs/recorder_YYYYMMDD.log` 에 한 줄씩(작업 이름 · status · 예외 형식 이름 · 비밀 없음) (Ruling: Final M4).
- 종료 코드: 0 정상·휴장 · 1 예외 · 2 가드 거부·07:50 전·`too_early`·`already_recorded`·동결 거부 · 3 잠금 사용 중(runner: main, EXIT2).

---

## §3. 특징

### 3-1. 주 특징 4 (단위 고정 · spec §4-3)

| # | 열 | 정의(KIS 원문 필드) | 단위 | D 행 | NULL 조건 | 나쁜 쪽 |
|---|---|---|---|---|---|---|
| ① | `f1_orgn` | investor `orgn_ntby_tr_pbmn` × **1,000,000** ÷ program `acml_tr_pbmn` | investor 금액 = 백만원 → ×1e6 = 원 · program = 원 → 비율(무차원) | 두 응답 모두 `stck_bsop_date == D` | D 행 없음 · 파싱 불가 · 분모 ≤ 0 | 하위 20% |
| ② | `f2_prog` | program `whol_smtn_ntby_tr_pbmn` ÷ program `acml_tr_pbmn` | 원 ÷ 원 | `stck_bsop_date == D` | 같음 | 하위 20% |
| ③ | `f3_short` | short(`output2`) `ssts_vol_rlim` | %(공매도 체결 수량 ÷ 거래량 · DOSSIER_B §3) | `stck_bsop_date == D` | D 행 없음 · 파싱 불가 | 상위 20% |
| ④ | `f4_credit` | credit `whol_loan_rmnd_rate` · 행 = `deal_date` == (§2-4 달력에서 D 의 **k 거래일 전**) | %(DOSSIER_B §3) | `deal_date` 정확히 일치 | k 미동결 · 그 날짜 행 없음 · 파싱 불가 | 상위 20% |

- 출처: (settings.py: INVESTOR_AMT_UNIT) (코드: features.compute) (spec §4-3) (DOSSIER_B §0-2·§0-3).
- 🔴 **필드 이름**: 스펙 표의 `ntby_tr_pbmn`·`loan_rmnd_rate`·`loan_gvrt` 는 공유 DB 표의 열 별칭이고, KIS 원문 필드는 `whol_smtn_ntby_tr_pbmn`·`whol_loan_rmnd_rate`·`whol_loan_gvrt` 다(DOSSIER_B §0-2). **이 문서는 원문 이름을 동결한다**(봉인되는 것이 원문이다).
- 분모 = 같은 아침 program 응답의 `acml_tr_pbmn`(분자·분모 시점 일치 · 08:40 의 `daily_prices` D 봉은 애프터마켓 전 판이다 · spec §4-3).
- 🔴 «첫 행» 금지 — 날짜 필드가 D 와 같은 행만 쓴다(spec §4-2) (코드: features.pick).
- 숫자 파싱: 쉼표 제거 · 빈칸·`-`·`+` = NULL · `0` 은 0(NULL 아님) (코드: features.num).

### 3-2. has_* 와 가용률

- `has_investor` = ① 이 계산됨 · `has_program` = ② · `has_short` = ③ · `has_credit` = ④ (코드: features.compute).
  - 🔴 `has_investor` 는 분모(program)까지 포함한다 — investor 응답이 있어도 program D 행이 없으면 false(SDD Task 4 minor · plan 그대로).
- run 행 `avail_X` = 그날 후보 행 중 `has_X` 비율(후보 0 이면 0) · `avail_credit` 은 k 가 정해지기 전까지 NULL(runner: _run_record).
- 스펙의 «수급 쪽 표지 = 자기 응답에 D 행 + 핵심 열 비NULL»(spec §4-4)이 이 has_* 다.

### 3-3. 탐색 열 (판정 아님 · 「탐색」 표시 · spec §4-3)

| 열 | 정의 | 단위 |
|---|---|---|
| `x_frgn` · `x_prsn` | investor `frgn_ntby_tr_pbmn` · `prsn_ntby_tr_pbmn` × 1e6 ÷ program `acml_tr_pbmn` | 비율 |
| `x_orgn5` | D 이하 investor 최근 5행의 `orgn_ntby_tr_pbmn` 합 × 1e6 ÷ 같은 날짜들의 program `acml_tr_pbmn` 합 · investor 행이 정확히 5개일 때만 | 비율(분자·분모 날짜 집합이 다를 수 있음 · SDD Task 4 minor) |
| `x_loan_gvrt` | ④ 와 같은 행의 `whol_loan_gvrt` | %(추정 · 트레이더 패널 「신용 공여율로 추정」) |
| `x_ssts_amt_rlim` | short D 행의 `ssts_tr_pbmn_rlim` | %(거래대금 대비로 추정 · 실측 미확인) |
| `acml_tr_pbmn` | program D 행 거래대금 | 원 |
| `credit_deal_date` | credit 응답의 `deal_date ≤ D` 중 가장 최근(YYYYMMDD) | — |
| `credit_lag` | D 와 `credit_deal_date` 의 거래일 차(§2-4 달력 · 달력에 없는 날짜면 NULL) | 거래일 |
| 원문 전부 | `raw.body` | — |

### 3-4. 신용 시차 k

- k = 「매수일 07:52 에 받은 신용 응답에서 쓰는 행이 D 의 몇 거래일 전 `deal_date` 인가」. 지금은 미정이다(settings.py: CREDIT_LAG_K = None). k 가 정해지기 전에는 봉인으로 넘어가지 않는다(코드: phase.seal_ready) (plan 「스펙과 다른 점」 3).
- 🔒 **결정 규칙**: 시험 단계에서 ok record 행이 있는 가장 최근 **10거래일**(settings.py: TRIAL_DAYS)을 쓴다. k ∈ {1, …, 6}(코드: phase.choose_k_table)마다 일별 가용률 = 「그날 후보 중 `credit_lag` 가 있고 ≤ k 인 비율」을 낸다. **최소 일 가용률 ≥ 0.95**(settings.py: AVAIL_MIN)인 **가장 작은 k** 를 고른다(plan Task 9 §3 · 출력 = `--choose-k`).
- 그런 k 가 없으면 멈추고 사장님께 보고한다(plan Task 11 Step 2) — 선택지 §9-5.
- **동결 1회**: `settings.CREDIT_LAG_K = k` 커밋 → 운영 워크트리를 새 커밋으로 detached 전환 → `--freeze`(봉인 행 0 이라 허용) (plan Task 11 Step 3). 이 커밋과 이 문서 동결 커밋의 차이는 `CREDIT_LAG_K` 한 줄과 §10 실행 기록 칸뿐이어야 한다(초안 해석). 봉인 시작 뒤 k 변경 = 새 rule_v(§9-6).
- 주의: 전환 판정의 신용 가용률은 «`credit_lag` ≤ k» 대리값이다(시험 행엔 ④ 가 없다). 봉인 뒤 `has_credit` 은 «D−k 행이 정확히 있음»이다. 30거래일 롤링 응답에서 둘이 갈리는 경우는 KIS 의 날짜와 §2-4 달력이 어긋날 때뿐으로 본다(초안 해석 · §6-5).

---

## §4. 시험 → 봉인 전환 (spec §4-1)

### 4-1. 시험 단계

- 운영 시작(plan Task 10) 첫 기록일부터 시험 표(`trial_*`)에 기록한다.
- 🔴 시험 값은 판정에 쓰지 않는다(spec §4-1). 시험 값 × 수익 결합도 하지 않는다(초안 해석 · spec §4-5 「개봉 전 결과 조회 금지」를 시험 값까지 넓힘).
- 매일 확인(EOD 한 줄 · plan Task 11 Step 1): record status · 가용률 4 · `snapshot_match` · late·missed_* 건수.

### 4-2. 전환 조건 (코드 그대로 · 매 record 실행 때 자동)

- 판정 대상 = 지금 기록하는 D 를 «뺀» 끝난 스캔일 **10개**(§2-4 달력에서 연속) (runner: `days_desc[1:1+TRIAL_DAYS]`) (Ruling: Final C1).
- 10일 각각이 아래를 모두 만족해야 한다(코드: phase.seal_ready):
  1. record 행 status = `ok`(`late`·`missed_*`·`error`·행 없음 = 불통과).
  2. min(`avail_investor`, `avail_program`, `avail_short`) ≥ **0.95**(settings.py: AVAIL_MIN).
  3. 신용 가용률(그날 후보 중 `credit_lag` ≤ k 비율) ≥ **0.95**.
  4. snapshot_check 행 status = `ok` ∧ `snapshot_match = true`(spec §4-1(a)).
- k 미동결이면 전환하지 않는다.
- 10일 모두 통과 → **그 실행의 D 부터** 봉인 표에 쓴다 = 「통과 다음 거래일」(spec §4-1).
- 🔒 **한 방향**: 봉인 run 행이 하나라도 생기면(상태 무관) 이후 계속 봉인이다(Ruling: Task 6 Important 1). 스냅샷 대조도 봉인 행이 있으면 봉인 표에 쓴다(Ruling: Final M1).
- 시점: 스펙은 ≈10-26~28 로 적었다(시험 시작 10-14 가정 · spec §4-1). 실제는 운영 시작일 + 시험 10거래일 + k 동결에 따른다.

### 4-3. 후보 0 인 시험일

- 코드: 후보가 0 이면 가용률 = 0(분모 max(1, 0))이고, 봇도 0건이면 스냅샷 행을 쓰지 않아 `no_snapshot` 이 된다(DOSSIER_B §2-4) ⇒ 그날은 «불통과»이고 연속 10일은 다시 센다.
- 🔒 초안 규칙 = **코드 그대로**(후보 0 인 시험일은 연속을 끊는다). 근거: 후보는 하루 27~48건(DOSSIER_B §2-4)이라 드물고, 「건너뜀」 규칙은 코드 수정이 필요하다. → 사장님 확인(보고 Q1).
- 봉인 단계에서 후보 0 인 날 = `ok` 행(후보 0) · 판정에선 「후보 < 10」으로 빠진다(§5-1).

### 4-4. 스펙 프로브 처리 (spec §4-1(c) · §4-2 ②)

| 프로브 | 처리 |
|---|---|
| 07:52 응답 첫 행의 날짜·NULL 여부 | 영향 차단 = D 행을 날짜로만 고른다(§3-1). 원문이 `trial_raw` 에 남아 시험 완료 보고에 비율을 인쇄한다(§4-5). |
| D 값의 B 07:52 vs B+1 07:52 동일 여부 | vintage 2 원문(§2-7)으로 인쇄한다(§4-5). |
| 신용 최신 `deal_date` 08:00 vs 16:00 | 🔴 **뺀다**(구현 안 함 · SDD Final M3). 대신 07:52 시험 기록의 `credit_lag` 분포로 k 를 정한다(§3-4) — 기록기가 실제로 보는 시각의 값이라, 판정에 필요한 것은 이것뿐이다. |
| D 가격 완결의 «표지 행 `updated_at`» | 🔴 **뺀다**(구현 안 함 · SDD Final M3). 대신 D/D′ 행 수 비 ≥ 0.98 ∧ 유니버스 날짜 = D(§2-5)와 시험 10일 스냅샷 100% 일치가 같은 위험(덜 들어온 D)을 잡는다. |

### 4-5. 시험 완료 보고 (인쇄만 · 판정 아님)

- 10일 k 표(`--choose-k`) · 날짜별 4조건 통과표.
- `trial_raw` 에서 SELECT 로만: (가) 응답 첫 행 날짜 ≠ D 비율 · D 행 핵심 열 NULL 비율(종류별) (나) vintage 1 vs 2 의 D 행 핵심 열 일치 비율(종류별).
- 시험 값 × 수익 결합 0.

---

## §5. 판정 (spec §4-5 · 봉인 행만)

### 5-1. 표본

- **날짜**: 봉인 단계 scan_date 중 정본 record(§2-8) status = `ok` ∧ §2-9 해시 검증 통과. `late`·결측일 제외.
- **행**: 그날 봉인 후보 행 ∩ **에피소드 첫 행** ∩ **band_ok** ∩ 그 특징 비NULL. 결측 행은 그 특징 검정에서 **제외**한다 — 「나머지」에 넣지 않는다(spec §4-5).
- **날 제외**:
  - 그날 봉인 후보 행 수 < **10** → 네 특징 모두에서 제외(spec §4-5 · 「후보」 = 그날 봉인 후보 행 수 `n_cands` 로 읽음 · 초안 해석).
  - 그날 그 특징 커버리지(봉인 후보 중 비NULL 비율) < **80%** → 그 특징에서만 제외(spec §4-5).
- **에피소드**: 같은 종목의 «연속 거래일» 후보 묶음이다. 후보 이력 = `screener_snapshots`(params_hash 고정 · 봇이 실제로 본 후보 · 시험일·결측일 포함) · 그날 스냅샷이 없으면 그날 기록기 후보 행(초안 해석). 표본은 첫 행만 쓴다(K2 의 P2 · `docs/prereg_2026-09-24_test_tool_calibration.md` §2).
- **꼬리**: 그날 그 특징이 비NULL 인 봉인 후보 «전부» 안에서 백분위 `rank(pct=True, method='average')` → 하위 꼬리 = pct ≤ 0.20 · 상위 꼬리 = pct > 0.80 · 동점 = 평균 순위(K2 의 P3 규칙을 20% 로 옮김 · 초안 해석). 분위는 08:40 에 필터가 실제로 볼 집합(그날 후보 전부)에서 매기고, 표본 제한(첫 행·band_ok)은 그 뒤에 건다.

### 5-2. 결과 — daytrading 매매 흉내 (spec §4-5 → §3-4)

- 체결(band_ok): 매수일 시가 ≤ D 종가 × 1.03 → 시가 · 시가 > 상한 ∧ 저가 ≤ 상한 → 상한가 · 그 밖 = 미체결(band_ok = false · 표본 밖) (`theme_rank/bandfill.py` 규칙).
- 청산: 체결가 **+10% / −10% / 최대 보유 10거래일** — `ledger8/exitsim8` daytrading 규칙.
- 동시 터치(같은 봉에 ±10% 둘 다): 분봉(`minute_candles`)이 있으면 분봉 순서로 정한다 · 없는 행은 «손절 우선»·«익절 우선» 두 판을 각각 계산한다(spec §4-5).
- 거래정지: 진입 봉 거래량 0 → «진입 불가»(표본 밖 · 따로 셈) · 보유 중 정지 → 재개 뒤 첫 체결가로 청산 · 창 끝까지 정지 → 마지막 값 + «미해소» 표시(spec §3-4).
- net = gross − **0.25%/건**(spec §3-4) — 상수라 δ 에는 영향이 없다(절대 손익 인쇄용).
- 가격 = `daily_prices` 원값(🔴 `adj_factor` 를 가격에 곱하지 않는다). 보유 중 권리락 처리 = 보고 Q5(§6-10).

### 5-3. 통계 — K2 도구 (spec §4-5)

- `δ̂_j` = 꼬리 평균 − 나머지 평균(§1) · SE = 에피소드 첫 행 표본에서 **종목 클러스터 CR1** · K2 = P3(날짜 안 분위) + P2(에피소드 첫 행 CR1) (검정 도구 교정 `candidate_ledger/tool_calibration/RESULTS.md` 「주 도구 = K2」).
- `p_j = Φ(δ̂_j / SE_j)`(단측 · δ < 0 쪽) · **Holm m = 4 · α = 0.05**(spec §4-5).
- 🔒 **자기 표본 가짜 게이트**(spec §4-5 → §3-5 규칙):
  - 가짜 특징 **3종 × 400** = G-종목 · G-날짜 · G-AR(생성식 = `docs/prereg_2026-09-24_test_tool_calibration.md` §2 표 그대로 · 단 G-AR 의 달력은 KOSPI 달력 대신 §2-4 달력 · 초안 해석).
  - 시드 = `numpy.random.default_rng([20261010, 20, t, i])` · t = 1 G-종목 / 2 G-날짜 / 4 G-AR · i = 1…400(초안 제안 · spec §3-5 「새 시드」 · A 의 `[20261010, 7, i]` 와 겹치지 않게).
  - 가짜 특징을 §5-1 표본 규칙(결측이 없으니 「후보 < 10」 제외만)에 넣고 같은 꼬리 20% 검정을 돌려 **양측 p < 0.10 거부율**을 낸다.
  - 세 거부율이 모두 **0.07~0.13** → CR1 을 쓴다.
  - 아니면 **2원 클러스터**(종목 × 20거래일 블록 · 블록 = 봉인 첫날부터의 거래일 순번 ÷ 20 의 몫 · 초안 해석)로 같은 게이트 → 통과면 2원 클러스터를 쓴다.
  - 둘 다 탈락 → 「판정 불가」(spec §3-5).
  - 게이트가 «구속»하는 시점 = 개봉 직전 · 판정 표본 그대로(초안 해석). 60일 블라인드 점검의 거부율은 인쇄만 한다.
- 동시 터치 두 판(§5-2)이 필요한 행이 있으면 두 판 각각 Holm 을 돌려, **둘 다** 라벨 조건을 만족할 때만 「있음」이다(초안 해석 · A 의 spec §3-7 규칙을 따름).

### 5-4. 일정 (spec §4-5)

- 봉인 n거래일 = 첫 봉인 scan_date 부터 §2-4 달력 거래일 수(결측일 포함 · 초안 해석).
- **블라인드 점검 = 봉인 60거래일 + 10 뒤**. 보는 것: n(특징별 표본 수) · 결측률(특징별·날짜별) · net 수익 SD(특징으로 나누지 않음) · 가짜 특징 3종 × 400 거부율 · `SD_null`. 🔴 특징 × 수익 결합 0.
  - `SD_null₆₀` = 60일 표본에서 가짜 3종 각각의 평균 CR1 SE 중 최댓값(초안 해석).
- **연장 공식**: 120일 예상 MDE = **3.083 × SD_null₆₀ × √(n₆₀ / n₁₂₀)** > **1.5%p** 면 판정 창을 **250거래일**로 1회 연장한다.
  - n₆₀ = 60일 첫 행∩band_ok 표본 수 · n₁₂₀ = n₆₀ × 120/60(같은 밀도로 투영 · 초안 해석).
  - 3.083 = z(1−0.0125) + 0.842(Holm 1단계 α 0.0125 · 검정력 0.8 · 퀀트 패널).
  - 연장 판단은 공식만 쓴다 — δ̂ 를 보지 않는다.
- **개봉 = 봉인 120(또는 250)거래일 + 10 뒤 1회**. 마지막 로트의 청산 창(exitsim8 최대 보유)이 닫힌 날의 일봉이 완결된 뒤여야 한다(초안 해석 = 스펙 「+10」의 뜻).
- 🔴 개봉 전 결과 조회 금지.
- 추정(spec §4-5): 봉인 ≈10-27 기준 블라인드 점검 ≈2027-02 초 · 판정 ≈2027-05 초.

### 5-5. 라벨 (특징마다 · spec §4-5)

- **「있음(나쁨)」** = Holm 조정 p < 0.05 ∧ δ̂ ≤ **−0.5%p** ∧ 앞·뒤 절반 δ̂ 부호 같음(둘 다 음수 · 절반 = 판정 창 scan_date 를 날 수로 반 나눔 · 초안 해석).
- 「없음」 = 선언 불가(이 설계로는 못 한다 · spec §4-5·§7).
- 그 밖 = **「판별 보류」** — 「쓸모없음」이 아니다.
- 게이트 탈락 = 「판정 불가」(§5-3).
- 참고 검정력(퀀트 패널 · 이미 본 원장으로 추정 · §7-1): 120거래일 SE 0.411 · Holm 1단계 MDE 1.27%p(결측 20% 면 1.42) · 250거래일 SE 0.285 · 0.88%p.

### 5-6. 통과했을 때 (각각 별도 결정 · spec §4-5 → §3-9)

- L-1 비열등(B 는 같은 120일 창) → L-2 페이퍼 그림자 20거래일 → L-3 안전장치 → L-4 실전(페이퍼 적용 60거래일 뒤 · 실전 첫 4주엔 넣지 않음 · theme_rank·TN1 과 같은 날 바꾸지 않음 · 적용일 전후 성적 구간 분리).
- 그때까지 라이브 코드 0줄.

### 5-7. 금지 (사후 완화 방지)

1. 개봉 전 봉인 특징 × 수익 결합(시험 값 포함).
2. 꼬리 비율(20%) · 방향 · Holm m · α · 라벨 문턱(−0.5%p) · 연장 공식 · 게이트 범위(0.07~0.13) · 표본 규칙(10건 · 80%) 변경.
3. NULL 메우기(vintage 2 · 공유 수급 표 · 나중 조회 포함) · 놓친 날 재기록.
4. 봉인 뒤 재동결(코드가 거부 · runner: run_freeze) · 봉인 뒤 k 변경.
5. 탐색 열로 라벨 정하기.
6. `--check-snapshot` 수동 재실행(§2-8).

---

## §6. 한계

1. B 는 큰 효과(≈1.3%p 이상)만 잡는다. 「없음」은 이 설계로 선언할 수 없다(spec §7).
2. 수급 값은 KIS 응답에 의존한다. 개정 여부는 vintage 2 로 «재기만» 한다. 신규상장은 KIS 응답이 있으면 들어간다(spec §7).
3. 효과가 진짜여도 «보험» 크기다(spec §1·§7).
4. 후보 복제의 정확성은 전향 시험으로만 증명된다. 지난날 재계산은 15:45 sweep 때문에 스냅샷과 다르다(§7-4 · DOSSIER_B §0-4). 봉인 뒤 불일치 날의 처리 = 보고 Q2.
5. 달력: 정적 달력에 없는 임시 휴장이 생기면, 그날 기록기가 돌아 D 를 하루 일찍 기록하고 다음 거래일은 `universe_stale`·`no_record` 가 된다(SDD Final residual). 덮어쓰기·오염은 없고 status 로 드러난다. 그 주변 `credit_lag` 도 하루 어긋날 수 있다.
6. DB 불변은 쓰기 역할 기준이다(슈퍼유저 예외 · §2-10).
7. 앱키 공유: 페이퍼 봇(07:40 기동)과 같은 앱키(초당 20건 한도)를 07:52~08:38 에 나눠 쓴다(DOSSIER_B §3) → `EGW00201` 재시도·지연 → `late` 가능.
8. `has_investor` 는 분모(program) 가용성을 포함한다(§3-2). `avail_investor` 만으로는 investor TR 장애를 구별할 수 없다(원문 `rt_cd` 로는 구별된다).
9. ① 은 0 이 많다(동결 전 본 것: 기관 순매수가 정확히 0 인 후보 64/224 = 29% · §7-1) → 동점 평균 순위라 하위 꼬리가 20% 보다 작을 수 있다. ④ 는 후보에 위험 구간(≥7%)이 드물다(0/172) → 「구별 안 됨」 예상. ③ 은 방향 확신이 낮다.
10. 결과 쪽 권리락: 보유 중 무상증자 권리락 날 가격이 반토막이면 −10% 손절이 기계적으로 난다(spec §9-1). `exitsim8` 에는 기업행위 보정이 없다(초안 확인 · grep). 처리 = 보고 Q5.
11. 라이브 7파일이 바뀌면 그날부터 기록이 멈춘다(§9-1). `api/kis_market_api.py` 는 08-01 이후 main 커밋 7개 · `api/kis_auth.py` 2개(초안 확인 · git log) — 봉인 기간 중 멈춤·재고정이 몇 번 생길 수 있다(보고 Q3).

---

## §7. 동결 전 본 것

### 7-1. 설계를 만든 사람들이 본 것 — 전부 고지

1. **`feature_study/RESULTS_2026-09-24.md:428-435`**(이미 공표된 인쇄 · 특징 × 수익 결합): daytrading `investor_trend_daily` 5일 순매수(itd5)의 3분위 T3−T1(%p · n=771 · 데이터 2026-07-03~09-21) — 기관 수량 +1.18 · 금액 +1.51 · 외국인 수량 +0.46 · 금액 +0.36 · 개인 수량 +0.15 · 금액 −0.10. 방향이 ① 가설(기관 순매수 적을수록 나쁨)과 같은 쪽이다. 🔴 ① 은 «이미 본 특징»이다(spec §5 · 퀀트 6). 창(2026-07~09)은 판정 창(봉인 ≈2026-10 말~)과 겹치지 않는다.
2. **전문가 패널(10-10) 숫자 전부**(spec §5) — B 관련:
   - 트레이더 B4(daytrading 스냅샷 09-28~10-06 · 224건 × 공유 수급 표 · 덮어쓴 최종값): 외국인 vs 프로그램 순매수 금액 상관 **0.968**(거래대금 대비 비율 0.959) · 기관 vs 프로그램 −0.098 · 개인 vs ①(외+기) −0.932 · 기관 순매수 정확히 0 인 후보 64/224(29%).
   - 트레이더 권고 4·5: 공매도 비중 후보 중앙값 0.51%(절반 < 0.5%) · 신용잔고율 후보 중앙값 1.68% · 상위 20% 경계 3.41% · ≥7% 0/172 · `loan_gvrt` 중앙값 10.0% · 상위 10% 21.9%.
   - 데이터 X1~X5·X7: 공유 표 5일 몰아 수집 · 16:0x 덜 끝난 값(investor D=10-06 2,750행 중 110행 수급 열 NULL) · 유니버스 08-14 고정(16종목 0행 · 그중 9개 daytrading 1차 통과) · 단위(005930 10-02 `frgn_ntby_tr_pbmn` −96,172 ↔ 수량×종가 −96.9e9원) · 신용 결제일 기준 3~4거래일 지연 · 지난날 재계산 ≠ 스냅샷.
   - 퀀트 5·권고: 수급 `created_at` 몰아 수집 실측 · B 검정력 표(2024-03~ 원장 가짜 특징 CR1 SE 밀도 보정): 60/120/250거래일 SE 0.594/0.411/0.285 · Holm 1단계 MDE 1.83/1.27/0.88 · α 0.05 MDE 1.48/1.02/0.71.
   - 이 숫자들 가운데 특징 × 수익 결합은 없다(특징끼리 상관 · 특징 분포 · 수집 시각 · 가짜 특징 SE 뿐).
3. **DOSSIER_B**(계획 조사 · 10-10 · 읽기만): 단위 실측(005930 10-06 기관 −52,296 백만원 · program `acml_tr_pbmn` 3,469,808,461,750원 vs `daily_prices.trading_value` 3,535,153,621,870원 = 애프터마켓 차) · 신용 16:0x 수집분 최신 `deal_date` = 3거래일 전 · 스냅샷 `created_at` = 다음 거래일 09:00:11~21 · 지난날 재계산(10-07 37 vs 36 · 점수 차 최대 47.9 · 10-06 52 vs 48 · 10-02 38 vs 36) · 라이브 `screener.py` 작업 사본 CRLF · 토큰 파일 YAML 2줄과 발급 시각 로그. 수급 값 × 수익 결합 0.
4. **B Task 8 실 DB dry-run**(10-10 · 읽기 전용 · KIS 0 · 세션 scratchpad 스크립트 · 후보 «종목·점수»만):

| D | 스냅샷 | 재계산 | 관계 | 비고 |
|---|---|---|---|---|
| 10-08 | 0행 | 33 | — | `d_complete` 2765/2765 · 10-08 스냅샷은 10-12 09:00 에 생긴다(설계와 일치) |
| 10-07 | 36 | 37 | 스냅샷 ⊂ 재계산 | 한 종목 점수 129.2 vs 114.8 |
| 10-06 | 48 | 52 | 스냅샷 ⊂ 재계산 | |
| 10-02 | 36 | 38 | 스냅샷 ⊂ 재계산 | |

   - 스냅샷에만 있는 종목 0 · 점수는 대체로 몇 % 이내 · 순위 일치는 3일 모두 거짓(표류 예상).
   - 재계산에만 있는 종목은 10-08 15:45 일괄 재수집(`updated_at`)과 부합한다. 다만 비율이 큰 3종목(126600 · 066980 · 348030)은 표류로 다 설명되지 않는다 ⇒ 정확 복제의 관문 = 시험 10일 전향 대조(§4).

### 7-2. 보지 않은 것

- B 구현(Task 1~8)과 이 초안 작성 중: KIS 호출 0 · 실 응답으로 계산한 특징 값 0(dry-run 은 스텁이라 전부 NULL) · `dtflow_shadow` 표 없음(DDL 미적용) · 특징(또는 공유 수급 표 값) × 수익 결합 0.
- 판정 창(봉인 뒤) 데이터는 아직 존재하지 않는다.
- 초안 작성자는 DB·KIS 에 접속하지 않았다. 읽은 것 = 스펙 · 계획 · 코드 · SDD 원장 · DOSSIER_B · 패널 BRIEF·EXPERT 3파일 · `feature_study/RESULTS_2026-09-24.md:415-444`(FD1 성분·재무비율 줄 포함 — B 특징 아님) · 검정 도구 교정 RESULTS·사전등록 발췌.

### 7-3. 서사에 영향을 준 것 (전부 고지)

1. 상관 0.968 → ① 을 「외국인+기관」(BRIEF)에서 「기관 단독」으로 바꾸고 ② 를 외국인 대용으로 뒀다(spec §8).
2. 신용 지연 실측 → ④ = 고정 시차 k(「그날 최신값」 금지 · 퀀트 5-②).
3. 공매도 중앙값 0.51% → ③ 「방향 확신 낮음」 표기(방향은 유지).
4. 신용 분포(≥7% 0/172) → ④ 「위험 구간 희소」 표기 · `loan_gvrt` 탐색 열.
5. itd5 인쇄(+) → ① 방향이 이미 본 쪽과 같다(방향 자체는 BRIEF 에서 이미 «낮을수록 나쁨»).
6. B 검정력 표 → 60일 블라인드 점검 → 120일 판정 + 연장 공식.
7. 지난날 재계산 불일치 → 시험 10일 전향 대조를 봉인 조건으로.

---

## §8. KIS 호출 — 태쏘 shadow 「KIS 0」 원칙에서의 이탈 선언 (spec §4-4)

- 태쏘 shadow 틀은 KIS 를 부르지 않는다(DB 만 읽는다). 이 기록기는 그 원칙에서 **벗어난다**.
- 이유: 공유 수급 표로는 «그날 아침 알 수 있던 값»을 봉인할 수 없다(5일 몰아 수집 · 덜 끝난 값 · 흔적 없이 덮어씀 · 유니버스 고정 · 단위 · spec §2-3 · 데이터 X1~X4). 그래서 매수일 아침에 후보 종목만 직접 받는다.
- 범위(동결): 조회 TR 4개만(§2-6) · 주문 TR 0 · 토큰 발급 0(읽기만) · 실전 인스턴스 토큰·키 0 · 호출 간격 ≥ 0.10초 · `EGW00201` 백오프 최대 3회 · 07:50~08:38 안에서만 시작 · 하루 ≈220~420회(vintage 1+2 · §2-6).
- 라이브 영향(추정): 페이퍼 봇과 같은 앱키·같은 토큰을 읽어 쓴다. 발급을 하지 않으니 토큰을 무효로 만들 경로가 없다. 남는 위험 = 초당 한도 공유(기록기 ≤10건/초 · 한도 20건/초 · DOSSIER_B §3) → 봇 쪽 `EGW00201` 재시도 가능성. 07:52 는 실전 인스턴스·NewsQuant(07:45)와 겹치지 않게 고른 시각이다(데이터 R1).
- 이 이탈은 이 기록기에만 해당한다. 다른 shadow 의 「KIS 0」 원칙은 그대로다.

---

## §9. 봉인 뒤 바뀌는 것 — 절차

### 9-1. 라이브 원본 7파일이 바뀌면 (Ruling: Final I2)

- 7파일 중 하나라도 LF 정규화 sha 가 `frozen.json` 과 다르거나 읽을 수 없으면 가드가 거부한다 → 그날 DB 행 0(run 행도 없음) · 경보 `guard_refused GuardError/source_sha`(또는 `source_unreadable`·`source_list`) · 일자 로그. 09:05 대조도 같은 가드라 거부한다. ⇒ 그날은 결측일(§2-8).
- 가드는 «디스크의 파일»을 본다 — main 체크아웃이 바뀐 다음 실행부터 멈춘다(봇 재기동과 무관).
- 관리자 순서(읽기만): ① 바뀐 파일·커밋 확인(git log · 동결 때 blob 과 diff) ② 아래 A/B 분류 ③ 사장님께 쉬운 한 장으로 보고 · 승인 문장을 받는다.

### 9-2. 분류 A — 의미 불변 → «소스만 재고정»

- 조건: 복제한 부분(스크리너 SQL·룰·파라미터·params_hash · 불가능봉 판정 · KIS 4 TR 의 경로·헤더·파라미터·응답 키 · 토큰 파일 형식)의 의미가 한 글자도 바뀌지 않았다(주석·다른 함수·로그 등).
- 🔒 사장님 승인 뒤: `frozen.json` 의 `sources` 중 «바뀐 파일의 sha 만» 새 값으로 · `code_sha`·`rule_v`·`credit_lag_k` 는 그대로 · 옛 `frozen.json` 한 줄을 `frozen_history.jsonl` 에 덧붙인 뒤 원자 교체(임시 파일 → `os.replace`) · `frozen_at` = 재고정 시각.
- `--freeze` 는 봉인 행이 있으면 거부하므로(Ruling: Task 7 「--freeze 재동결 거부」) 이 재고정은 «수작업 1회»(또는 사장님이 승인한 일회성 스크립트)다 → 보고 Q3.
- §10 재고정 이력 표에 (날짜 · 파일 · 옛/새 sha 앞 12자 · 라이브 커밋 · 분류 근거 한 줄 · 사장님 승인 문장)을 적고 이 문서에 커밋한다.
- 재고정 전 결측일은 나중에 채우지 않는다.

### 9-3. 분류 B — 의미가 바뀜 → 새 rule_v 또는 종료

- B-1 스크리너 의미가 바뀜(룰·파라미터·유니버스·params_hash): 복제가 봇 후보와 더는 같지 않다.
- B-2 KIS 호출 의미가 바뀜(경로·헤더·파라미터·토큰 형식): 기록기 코드를 고쳐야 하고, 새 `code_sha` 는 봉인 행이 있는 rule_v 에서 재동결할 수 없다.
- 어느 쪽이든 v1 은 변경이 발효된 날의 직전 스캔일까지로 닫는다. 사장님 선택:
  - (가) 새 rule_v(`v2`) = 코드 수정 → 사전등록 개정 → 시험 10일부터 다시 → v2 는 별도 판정(v1 과 합치는 것은 별도 결정).
  - (나) 연구 종료 = v1 봉인분만으로 §5 일정대로 판정(표본이 모자라면 「판별 보류」).
- 애매하면 B 로 본다(보수).

### 9-4. 정본 충돌 (§2-8)

- snapshot_check 행이 한 날 여럿이고, 정본(가장 이른 행)과 코드가 쓴 행(마지막 ok 행)이 갈려 전환 결과가 달라지면 → 관리자 보고 → 사장님 결정(봉인 유지 vs 새 rule_v).

### 9-5. k 가 정해지지 않을 때 (시험 단계)

- 시험 10일 뒤 k ∈ 1..6 중 최소 일 가용률 ≥ 0.95 가 없으면 멈추고 보고한다(plan Task 11 Step 2). 선택지(사장님 · 보고 Q4): (가) ④ 를 빼고 m = 3 으로 개정 (나) 시험 연장(같은 규칙 · 가장 최근 10 ok 일로 다시) (다) 중단.
- k 없이 봉인으로 넘어가는 것은 코드가 막는다(§4-2).

### 9-6. k · 코드 변경

- 봉인 «전» k 를 다시 고르는 것 = 사전등록 개정(사장님 승인) + 재동결(코드 허용).
- 봉인 «뒤» k·코드 변경 = 새 rule_v(§9-3).

### 9-7. KIS 응답·DB 사고

- KIS 응답 형식이 바뀌면(라이브 파일 변화 없이) has_*·`n_fail`·`rt_cd` 로 드러난다. 봉인 뒤 코드 수정은 새 rule_v 다. 커버리지 < 80% 인 날은 §5-1 로 자동 제외된다. 오래 가면 사장님이 정한다.
- 해시 검증(§2-9)에서 어긋난 날 = 표본 제외 + 보고.

---

## §10. 실행 기록 (동결 뒤 채운다)

| 항목 | 값 |
|---|---|
| 이 문서 동결 커밋 · 사장님 동결 문장 | (동결 때) |
| 운영 워크트리 | `D:/tmp/kis-wt-dtflow-run`(detached) |
| 시험 첫 기록일 | |
| k · 최소 일 가용률 · k 동결 커밋 | |
| 봉인 첫 scan_date | |
| 블라인드 점검일(60 + 10) | |
| 판정 창(120 / 250) · 개봉일 | |

**재고정 이력(§9-2)**

| 날짜 | 파일 | 옛 sha(12) | 새 sha(12) | 라이브 커밋 | 분류 근거 | 사장님 승인 문장 |
|---|---|---|---|---|---|---|

---

## 부록 A — `ddl.sql` 전문

- 바이트 그대로 옮겼다(`RoboTrader_template/backtest/concept_axes/dtflow_shadow/ddl.sql` · 커밋 `394eeb6` · LF · sha256 `0fa4fb21f3575b4904754792a87fa5aae91a676248223c647d6818f6f336f7b5`).
- 실행은 사장님 확인 뒤 1회(plan Task 10 Step 2).

```sql
-- 실행(사장님 확인 뒤 1회 · Task 10): psql -h 127.0.0.1 -p 5433 -U postgres -d kis_template -f ddl.sql
-- 비밀번호는 실행 중 \prompt 로 받는다 = config/key.ini [DTFLOW_SHADOW] db_password 값(또는 -v dtflow_pw=…).
--   빈 값이면(비대화형 실행에서 \prompt 가 빈 줄을 읽은 경우 포함) 아무것도 만들지 않고 멈춘다.
-- 규약: retention 없음 · DROP 없음 · IF NOT EXISTS 없음(이미 있으면 멈춘다).
-- 권한: 스키마·표 6개의 소유자 = NOLOGIN 역할 dtflow_shadow_owner(비번 없음 · 접속 불가).
--   로그인 쓰기 역할 dtflow_shadow_writer(비번이 key.ini 에 있음) = 표 6개 INSERT·SELECT 만
--   (UPDATE·DELETE·TRUNCATE·DROP·소유 없음 → 봉인 행은 쓰기 역할로 바꾸거나 지울 수 없다 · ON CONFLICT DO NOTHING 은 INSERT 만 필요).
--   robotrader = SELECT.
\set ON_ERROR_STOP on
\if :{?dtflow_pw}
\else
\prompt 'dtflow_shadow_writer password (key.ini [DTFLOW_SHADOW] db_password): ' dtflow_pw
\endif
SELECT (length(btrim(:'dtflow_pw')) > 0) AS dtflow_pw_ok \gset
\if :dtflow_pw_ok
\else
\echo 'dtflow_pw 가 비어 있다 — 아무것도 만들지 않고 중단'
DO $$ BEGIN RAISE EXCEPTION 'dtflow_pw empty — stop'; END $$;
\endif
CREATE ROLE dtflow_shadow_owner NOLOGIN;
CREATE ROLE dtflow_shadow_writer LOGIN PASSWORD :'dtflow_pw';
CREATE SCHEMA dtflow_shadow AUTHORIZATION dtflow_shadow_owner;
REVOKE ALL ON SCHEMA dtflow_shadow FROM PUBLIC;
GRANT CONNECT ON DATABASE kis_template TO dtflow_shadow_writer;
GRANT USAGE ON SCHEMA public TO dtflow_shadow_writer;
GRANT SELECT ON public.daily_prices, public.stock_info, public.screener_snapshots TO dtflow_shadow_writer;
SET ROLE dtflow_shadow_owner;
CREATE TABLE dtflow_shadow.trial_candidates (rule_v text, scan_date date, stock_code text, rank int, score double precision,
  run_at timestamptz, f1_orgn double precision, f2_prog double precision, f3_short double precision, f4_credit double precision,
  credit_deal_date text, credit_lag int, has_investor boolean, has_program boolean, has_short boolean, has_credit boolean,
  x_frgn double precision, x_prsn double precision, x_orgn5 double precision, x_loan_gvrt double precision,
  x_ssts_amt_rlim double precision, acml_tr_pbmn double precision, late boolean, code_sha text NOT NULL, row_sha text NOT NULL,
  PRIMARY KEY (rule_v, scan_date, stock_code));
CREATE TABLE dtflow_shadow.trial_raw (rule_v text, scan_date date, stock_code text, kind text, vintage smallint,
  fetched_at text, rt_cd text, msg_cd text, body jsonb, body_sha256 text NOT NULL,
  PRIMARY KEY (rule_v, scan_date, stock_code, kind, vintage));
CREATE TABLE dtflow_shadow.trial_run (rule_v text, scan_date date, run_kind text, run_at timestamptz, status text NOT NULL,
  n_cands int, n_calls int, n_fail int, avail_investor double precision, avail_program double precision,
  avail_short double precision, avail_credit double precision, snapshot_match boolean, snapshot_n int, mine_n int,
  max_score_diff double precision, universe_date text, d_rows int, dprev_rows int, rows_sha256 text, duration_ms int,
  code_sha text NOT NULL, error_text text, PRIMARY KEY (rule_v, scan_date, run_kind, run_at));
CREATE TABLE dtflow_shadow.candidates (LIKE dtflow_shadow.trial_candidates INCLUDING ALL);
CREATE TABLE dtflow_shadow.raw (LIKE dtflow_shadow.trial_raw INCLUDING ALL);
CREATE TABLE dtflow_shadow.run (LIKE dtflow_shadow.trial_run INCLUDING ALL);
RESET ROLE;
REVOKE ALL ON ALL TABLES IN SCHEMA dtflow_shadow FROM PUBLIC;
GRANT USAGE ON SCHEMA dtflow_shadow TO dtflow_shadow_writer;
GRANT INSERT, SELECT ON dtflow_shadow.trial_candidates, dtflow_shadow.trial_raw, dtflow_shadow.trial_run, dtflow_shadow.candidates, dtflow_shadow.raw, dtflow_shadow.run TO dtflow_shadow_writer;
GRANT USAGE ON SCHEMA dtflow_shadow TO robotrader;
GRANT SELECT ON ALL TABLES IN SCHEMA dtflow_shadow TO robotrader;
```
