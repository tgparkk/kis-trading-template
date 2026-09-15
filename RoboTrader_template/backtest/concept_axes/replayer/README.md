# 매수후보 원장 재현기 — `ma20` · `daytrading`

> 설계서 **정본** = `docs/superpowers/specs/2026-09-14-candidate-ledger-replayer-design.md` **v0.5**
> `flag_cliff` **정본** = `backtest/concept_axes/_defs/flag_cliff.sql` (= `FD1` §3-4-b 규약 1-b)
> 🔴 이 README 는 **도구 사용법**이다. 판정 절·문턱의 정본은 설계서와 사전등록 문서에 있다.

---

## 0. 🔴 먼저 읽을 두 줄

1. **「후보 ≠ 매수가능」** — 이 원장의 한 행은 **「그날 살 수 있었던 종목」이 아니다.**
   `screener_snapshots` 와 **같은 지점 = 안전필터 «이전»** 을 재현한다. 거래정지·VI·관리종목·
   정리매매 배제는 그 뒤 09:00 등록 단계(`core/candidate_selector.py`)에서 일어난다.
   라이브 실측(2026-08-10): 조회 71건 중 **6건(고유 5종목 ≈ 8.5%)** 이 등록 단계에서 배제됐다.
   ⇒ ***이 원장으로 「노출」·「보유」·「매수 가능」을 계산하면 8~9% 를 과대계상한다.***
   노출을 재려면 `virtual_trading_records` 를 써야 한다.
2. **전방 수익률이 «없다»** — 출력은 «기준일 D 이하» 정보뿐이다(`ret_5d` 는 **후방** 수익률
   `close[D]/close[D−5]−1` 이다). PnL·체결·사이징 경로는 **코드에 존재하지 않는다**
   — `BookBacktester` 를 import 하지 않는다(설계서 §0-2 · §8-1).
   결과 변수는 소비 문서(`FD1`·`NW1`·`NW2`)가 **따로** 조인한다.

---

## 1. 실행법

```bash
# 워크트리에서만. 라이브 트리(D:/GIT/kis-trading-template)에서 실행 금지.
cd <worktree>/RoboTrader_template

# ① 원장 생성 (판정 창 + 인쇄 전용 구간까지)
python backtest/concept_axes/replayer/run.py \
    --strategy both --start 2024-03-13 --end 2026-09-11 \
    --out ../scratchpad/replayer

# ② 일치율 게이트 (라이브 screener_snapshots 대조)
python backtest/concept_axes/replayer/run.py \
    --strategy both --gate --start 2026-06-05 --end 2026-09-11 \
    --out ../scratchpad/replayer_gate
```

| 옵션 | 뜻 |
|---|---|
| `--strategy ma20\|daytrading\|both` | 대상 전략 |
| `--start` / `--end` | 스캔 창. 기본 `2024-03-13` ~ `2026-09-11` |
| `--hist-start` | 워밍업 시작. 기본 `2021-01-01` — **스모크에서만 줄인다** |
| `--out` | 산출 디렉터리 (🔒 Q7: 원장은 `scratchpad/` 에 두고 **커밋하지 않는다**) |
| `--gate` | §4 일치율 게이트 모드 |

### 🔴 실행 전 확인 3가지

- **V5-a 실행 시간창** — 평일 **09:00~09:20 KST 를 포함하면 실행이 거부된다**(`RuntimeError`).
  09:00 장전 수집이 종목당 과거 ~103봉을 UPSERT 하고, ma20 90봉·daytrading 60봉이 **그 안에 전부
  들어간다**. 권장 창 = **07:00~08:40** 또는 **15:45~23:59**.
- **DB 는 SELECT 전용** — 커넥션이 `readonly` 로 열린다. env 는 `TIMESCALE_HOST`·`TIMESCALE_PORT`·
  `TIMESCALE_USER`·`TIMESCALE_PASSWORD` 넷뿐이고 **전부 기본값이 있다**(`.env` 불필요).
  DB명은 하드코딩하지 않고 `config.constants.resolve_daily_source_db()` 를 경유한다.
  앱키·계좌 등 비밀은 **쓰지 않는다**.
- **V5-b 지문 2회** — 실행 «직전»·«직후» 에 스냅샷 지문을 떠서 **같을 때만 산출물이 유효**하다.
  다르면 리포트가 「🔴 불일치 — 산출물 폐기·재실행」으로 찍힌다.

---

## 2. 구조 — 왜 「하이브리드」인가

| 모듈 | 하는 일 |
|---|---|
| `loader.py` | 일봉 벌크 로드 · 거래일 달력 · 유니버스(폴백 포함) · §1-2-b 배제 분류 · 스냅샷 지문 |
| `scan.py` | 날짜별 스캔 루프 · 창 자르기 · 위생 가드 · 정렬/절단/동점 |
| `flags.py` | `flag_locked_limit`·`flag_padding`·`flag_cliff`·후방 수익률·연도별 드리프트 집계 |
| `ledger.py` | §3 출력 스키마 조립 · `ledger_candidates.{csv,parquet}` · `ledger_diag.csv` |
| `gate.py` | M1~M4 · 노출/보호 구간 분할 · C1~C6 분류 · V5-a · V6-3/V6-5 |
| `run.py` | CLI · 지문 2회 · 리포트 md |

🟢 **판정 경계는 라이브 코드를 import 해서 «그대로» 부른다** — `base_filter()` · `default_params()` ·
`match()`. 셋 다 DB 를 안 건드리고(`QuantDailyReader` 는 lazy) 순수하게 DataFrame 만 본다.
⇒ ***룰 복제본이 «없으므로» 설계서 §2 (b) 의 드리프트가 구조적으로 불가능하다.***
🔴 재구현한 것은 **스캔 루프·벌크 로드·창 자르기·정렬**뿐이다. 라이브 코드는 **0줄** 바뀌지 않았다.

### 창과 단위 — 값이 갈리는 자리

| 전략 | `lookback_days` | 룰 최소 봉 | 위생 가드 창 | `score` |
|---|---|---|---|---|
| `book_pullback_ma20` | **90** | 32 | **90봉 전체**(`sanity_window=None`) | `mean(volume[-20:])` |
| `daytrading_3methods_breakout` | **60** | 17 | **60봉 전체** | `volume[-1] / mean(volume[-21:-1])` |

- `volume` 은 로더에서 **한 번만** `× COALESCE(adj_factor,1)` 한다(이중조정 금지).
  ⚠️ 가격(`open/high/low/close`)에는 **곱하지 않는다**(가짜 절벽).
- `trading_value` 는 **저장 컬럼을 쓰지 않고** `close × (volume × COALESCE(adj_factor,1))` 로 계산한다.
- 위생 가드 문턱 = `IMPOSSIBLE_DROP_PCT = -0.35`, **하락만**.

---

## 3. 출력 스키마 — `ledger_candidates.csv` / `.parquet`

1행 = **(전략, 기준일, 종목)**. 조인 키 = `(stock_code, scan_date)`.

| 컬럼 | 뜻 |
|---|---|
| `strategy` · `scan_date` · `stock_code` | 기준일 D = 마지막 «확정» 일봉 날짜(라이브 `screener_snapshots.scan_date` 와 같은 의미) |
| `rank` · `in_top_k` | score 내림차순 1-based · 동점은 **코드 오름차순**. `in_top_k` = `rank ≤ 5`(라이브 K) |
| `score` · `reason` | 룰이 돌려준 값 그대로 |
| `market` | ⚠️ **현행 스냅샷 · PIT 아님**(`stock_market` 은 이력이 없다). 층화·인쇄 전용 |
| `volatility_20d` | 🔒 FD1 필수 — 「플래그군 vs **변동성 동분위** 대조군」에 바로 붙는다 |
| `in_judgment_window` | `scan_date ≤ 2026-05-31`. `false` 행은 **판정 밖 · 게이트/인쇄 전용** |
| `flag_name_unknown` | `stock_info` 로 이름이 안 붙는 종목. 🔴 **배제가 아니라 표시** — 이름 기반 규칙이 «작동하지 않았다»는 뜻 |
| `flag_locked_limit` | 상·하한가 **잠김봉**: OHLC 동일 ∧ `volume > 0` |
| `flag_padding` | 거래정지 **패딩봉**: OHLC 동일 ∧ `volume = 0` |
| `flag_cliff` | **권리락 절벽(데이터 주도)** — 정본 `_defs/flag_cliff.sql` 과 **같은 식** |
| `cliff_unknown_nprior` · `cliff_unknown_adjstep` | 「없다」가 아니라 **「모른다」** — 직전 20봉 부족 / 창 안 `adj` 계단 |
| `flag_corp_action` | `corp_events` 조인 히트. ⚠️ **`flag_cliff` 와 다른 칸**(2026-07 6배 점프 = 수집 변경) |
| `flag_merge_suspect` | x5 merge 절벽 4종목(196450·297570·332290·083640). 고치지 않고 표시만 |
| `ret_5d` | **후방** `close[D]/close[D−5]−1` (거래일 기준) |
| `trading_value` · `market_cap` · `close`/`open`/`high`/`low`/`volume_adj` | D 행 값 |
| `n_bars` | 룰에 넘긴 창의 실제 봉 수 |
| `universe_eff_date` · `universe_fallback` | 라이브 폴백 재현 — D 당일 퀀트 적재가 안 끝났으면 직전 완전 퀀트일을 쓴다 |
| `run_id` · `git_sha` · `db_fingerprint_hash` · `replayer_params_hash` | 재현성 메타 |

**부속** `ledger_diag.csv`: 날짜별 `n_universe`·`n_universe_raw`·`n_eligible`·`n_impossible`·
`n_evaluated`·`n_matched`·`n_selected`·`n_tie_at_20`·`universe_fallback`.

🔴 **`fund_join_key` 는 따로 두지 않는다** — `(stock_code, scan_date)` 두 컬럼이 그 키다.
**재현기는 재무를 조인하지 않는다.** 소비 문서가 `dart_financials_asfiled` 를 `rcept_dt < scan_date`
로 건다.

---

## 4. 게이트 리포트 읽는 법 (`GATE_REPORT_<날짜>.md`)

### 4-1. 문턱은 **실행 «전»** 동결이다

| 지표 | 정의 | 🔒 문턱 |
|---|---|---|
| **M1** | 일별 집합 Jaccard, **마이크로 평균** = Σ교집합 / Σ합집합 | ≥ **0.98** PASS · 0.95~0.98 조건부 · **< 0.95 FAIL** |
| **M2** | 교집합 원소의 `rank` Spearman ρ, 날짜별 **중앙값** | ≥ 0.98 (원소 2 미만인 날은 분모에서 빼고 그 날짜 수를 인쇄) |
| **M3** | `top5(L) ∩ top5(R) / 5` 마이크로 평균 | ≥ **0.95** — 🔑 판정이 실제로 서는 자리가 K=5 다 |
| **M4** | 교집합 원소의 `\|score_R/score_L − 1\| ≤ 1e-6` 인 행 비율 | ≥ **99%** |

🔑 **M4 는 «원인 분리 장치»다** — ***M4 가 깨지면 원인은 데이터 갱신, M1 만 깨지면 원인은 룰·경계.***
🔴 **문턱을 내려서 통과시키지 않는다.** 미달이면 §4-5 분류표와 함께 **보고**한다.

### 4-2. 한 값으로 읽지 않는다 — 구간 분할이 «필수»

| 분할 | 경계 | 왜 |
|---|---|---|
| 노출 / 보호 | `≤ 2026-09-02` vs `≥ 2026-09-03` | 커밋 `7abdc30`(`W1_PAST_ROWS_INSERT_ONLY`)이 과거 행 UPSERT 채널을 닫았다 |
| 우선주 온보딩 | `≤ 2026-08-04` vs `≥ 2026-08-05` | 08-05 에 우선주 **+67 일괄 등장**(수집 확대이지 상장이 아니다) |
| daytrading params | `~06-22`(`high_window=20`) vs `06-23~`(15) | 창 «안»에서 파라미터가 바뀌었다 |

### 4-3. 불일치는 **양방향 집합 차분**으로 본다

「몇 %」가 아니라 `live_only` / `replay_only` 를 **둘 다** 인쇄한다 — *「더 많다」≠「포함한다」*.

| 라벨 | 뜻 |
|---|---|
| **C1** 데이터 갱신 | `created_at > scan_date + 3일` 또는 행 해시 차분. 🔴 **`updated_at` 은 쓰지 않는다**(전 행 단일 일자 = 판별력 0). M4 불일치는 **«동반» 서명**이지 단독 서명이 아니다 |
| **C2** 유니버스 일자 폴백 | 집합이 통째로 어긋남 · `universe_fallback` |
| **C3** 불가능봉 가드 차 | 그 종목이 재현기 가드에 걸려 제외됐다 |
| **C4** 룰 드리프트 | `params_hash` 구간 경계에 몰림 |
| **C5** 동점 경계 | rank 19~20 · score 동일 |
| **C6** 미상 | 위 어디에도 안 걸림 |

🔴 **`excl_1_2_b` 칸은 C 라벨이 아니다** — §1-2-b(우선주·리츠·외국주·ETF) 배제는
**사전등록된 «의도적» 차이**다. 라이브 `STOCK_ONLY` 정규식은 이들을 거르지 않으므로
그 종목은 **항상 `live_only` 로 나온다**. 이걸 C6 으로 세면 「미상」이 부풀려진다.

### 4-4. PASS·조건부·FAIL

- **PASS** = M1 ≥ 0.98 ∧ M3 ≥ 0.95 ∧ M4 ≥ 99%.
- **조건부 통과**는 설계서 §4-6 3 의 **조건 ①~⑧ 을 «전부» 인쇄**했을 때만 «제안»할 수 있다.
  특히 ④ **노출 구간 M1 ≥ 0.90** · ⑤ **보호 구간 ≥ 15거래일** · ⑥ **1회 한정** ·
  ⑦ **건별 🔒 사장님 승인**. 🔴 **M4 ≥ 99% 인데 M1 이 깨지면 조건부 통과 제안 «불가»**
  (원인이 데이터가 아니라 룰·경계이기 때문).
- **FAIL** = M1 < 0.95. ⇒ 판정(FD1·NW1·NW2) **착수 금지**.

### 4-5. V6 — 라이브 스냅샷이 «없는» 구간

> **V6 가 검증하는 것은 «라이브와 같은가»가 아니다** — 그 구간엔 대조할 원본이 0행이다.
> V6 가 검증하는 것은 ①재현기가 룰을 옳게 «계산»하는가 ②입력 데이터가 구간 간 «동질»한가 둘이다.

- **V6-3 연속성** — `n_universe`·`n_eligible`·`n_matched` 의 60일 이동중앙값 대비 ±50% 이탈일 **전수**.
- **V6-4 모집단 불연속** — 우선주 종목-일 수 **월별**(정본 식 vs 거친 식의 차이 포함).
- **V6-5 측정기 드리프트** — 연도별 **거래일당 패딩**. 🔴 **연도 간 비가 2배를 넘으면
  「후보 선택과 꼬리 측정이 시간에 따라 다른 자로 재졌다」를 판정문에 병기하고 연도 pooled 판정을 금지**한다.
  2021~2023 구간과의 pooled 검정은 **어떤 경우에도 금지**(공정 경계 — 패딩이 2024-03-12 6행 → 03-13 37행).

---

## 5. 테스트

```bash
# 워크트리에서만. 라이브 트리에서 pytest 금지.
python -m pytest backtest/concept_axes/replayer/tests -q            # 전부(DB 포함)
python -m pytest backtest/concept_axes/replayer/tests -q -m "not db"  # DB 없이
```

- `test_flag_cliff_sql_parity.py` 가 **정본 SQL 과 pandas 구현을 실 DB 에서 양방향 차분 0** 으로 고정한다.
- `test_integration_one_day.py` 는 라이브 하루를 재현해 M1~M4 를 **인쇄**만 한다(판정 언어 없음).
- 🔴 이 테스트들은 `backtest/concept_axes/replayer/tests/` 에 **격리**돼 있어
  `pyproject.toml` 의 `testpaths = RoboTrader_template/tests` 기준선 실패 집합을 흔들지 않는다.

---

## 6. 안 만드는 것 (🔴 명시)

| 안 만든다 | 근거 |
|---|---|
| 포지션 사이징 반사실 | 🔒 C-6. 러너가 포트폴리오를 재현하지 않는다 ⇒ 비(比)가 불변 = 주검정의 단조 재표현 |
| 체결·슬리피지·호가 | 원장은 「누가 후보였나」만 담는다 |
| 손익(PnL) | 🔴 실행 경로에 `BookBacktester` 가 **없다**(경로가 없어야 「없다」가 증명된다) |
| 매매 시뮬레이터 | 🔑 ***일치율 게이트는 후보 목록만 대조한다 — 게이트가 안 덮는 코드가 판정문을 만들면 안 된다*** |
| 라이브 배선·shadow 로그 변경 | 판정 후 별도 PR |
| 관리종목·VI·거래정지 배제 | 🔴 DB 에 없다(C-8). **고치지 않고 §0 「후보 ≠ 매수가능」으로 병기**한다 |
