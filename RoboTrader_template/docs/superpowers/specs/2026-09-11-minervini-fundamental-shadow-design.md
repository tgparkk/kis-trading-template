# minervini — 재무 «순위» 그림자(F_shadow) 배관 : 설계 (2026-09-11)

> 사장님 결정(2026-09-10 밤, 메모리 `decision-2026-09-10-fundamentals-track-b-and-tasso-6` §A):
> ①**트랙 B 착수**(라이브 룰 0줄) ②**9/29 부터 `F_shadow` 기록 → 10/19 발효 판단** ③**층 = «순위»**.
> 사전등록(미동결): `backtest/concept_axes/minervini/PREREG_FUNDAMENTAL_RANK.md`.
> 근거: 자문 `docs/전문가자문_재무섹터_쉬운설명_2026-09-06.md` §4~§8 · 판정 `backtest/concept_axes/minervini/RESULTS.md` §4-2.
> 범위 = **minervini 하나**. 계획서 `docs/plan_2026-09-05_focus3_roadmap.md` §2-(f) 의 **B-1b + B-1c 그림자 절반**.
> 형식은 선례 `2026-09-10-rsleader-corp-action-exclusion-design.md` 를 따른다.
>
> 🔴🔴 **9/22 전 minervini 코드 머지 금지.** 9/22(화)가 TT 게이트 `on` 20거래일째 판정일이고(`86ff02d` 발효 2026-08-26), 이 브랜치가 건드리는 파일이 **그 판정의 산출 경로 그 자체**다. 워크트리에서 만들되 **머지는 9/22 판정 뒤**, **발효(shadow 전환)는 9/29** — 둘 다 **별도 승인**.

---

## 0. 결정된 것 / 이 문서가 판정하는 것

**결정(바꾸지 않는다)**

1. 층은 **순위**다. `base_filter()` 가 아니다. **후보 집합은 불변.**
2. 이번 범위는 **기록(shadow)까지**다. 발효(정렬 실제 적용)는 10/19 판단 뒤 별도 결정.
3. 롤백 스위치 상수 **1개**(3모드). 기본값 **`off`**.
4. **청산·매수 판정 경로는 한 줄도 안 건드린다** — `evaluate_entry` · `evaluate_sell_conditions` · `_check_sell` 불변.

**이 문서가 판정하는 것** — Q1 읽기 경로 · Q2 소스 원장 · Q3 배선 층 · Q4 `on` 모드 구현 범위 · Q5 계기 로그 · Q6 RS 와의 비결합 · Q7 범위 밖 명시.

**이 변경의 정체 규정**: 이건 **관측 배관**이지 룰 변경도 알파 주장도 아니다. 근거는 「이렇게 하면 성과가 좋아진다」가 아니라 「**켜기 «전»에 배관·노출·원장 신선도를 실측한다**」이다. 선례는 TT 배선의 `shadow` 단계(`e5a868c` → 관측 5행 → `86ff02d`)이고 **같은 순서를 반복한다.**

---

## 1. 현재 구조 (전부 파일:줄)

### 1-1. minervini 후보 경로

| # | 단계 | 코드 |
|---|---|---|
| S0 | 어댑터 생성 | `runners/_adapter_factory.py:39-40` |
| S1 | `scan(scan_date, params)` — 카운터 초기화 후 base 위임 | `strategies/minervini_volume_dryup/screener.py:215-217` |
| S2 | `base_filter` — 시총 ≥3천억 · 거래대금 ≥30억 | `screener.py:84-94` |
| S3 | `_prepare_frame` — 일봉 260봉 + 불가능봉 가드(창 90봉) | `_rule_screener_base.py:161-184` (`screener.py:49`·`:53`) |
| S4 | **`build_context`** — 그날 프레임 «전체»로 RS 백분위 산출 | `screener.py:97-128` |
| S5 | `match` — dryup → (mode≠off) TT → `(score, reason)` | `screener.py:130-172` |
| S6 | **정렬 + topK** `scored.sort(...)` · `scored[:max_candidates]` | `_rule_screener_base.py:147-148` |
| S7 | `finalize_scan` — `TT게이트` 진단 1줄 + 죽은 가드 경보 | `screener.py:175-213` |

- 🔑 **`wants_context = True`**(`screener.py:60`) 라 base 가 **2패스**로 돈다(`_rule_screener_base.py:112-125`): ①적격 종목 일봉을 전부 모으고 ②`build_context` 로 횡단면 값을 만든 뒤 ③`match` 를 돈다. ⇒ ***재무를 「스캔당 1회 조회」로 넣을 자리가 이미 열려 있다.***
- 🔴 **RS 백분위의 분모가 「그날 `base_filter` 통과 집합」으로 못박혀 있다**(`screener.py:102-104`). `F` 를 `base_filter` 에 넣으면 실측상 분모가 **384 → 112**(scan_date 2026-09-09) 로 줄어 **`rule_trend_template` 의 8번째 조건이 다른 함수가 된다** ⇒ ***9/22 TT 판정 오염***(rs_leader 스펙 §7-2 가 남긴 경고와 같은 것).
- 라이브 절단은 **20 → 10 → K=3**(`config/constants.py:200` · `bot/candidate_loader.py:139` · `config.yaml` `max_positions: 3`). TT `on` 이후 후보가 하루 **2~8건**이라 ***실제로 걸리는 절단은 K=3 하나뿐이다.***

### 1-2. 매수 시점 경로 (재무가 들어가지 «않는» 곳)

- `MinerviniVolumeDryupStrategy.evaluate_entry`(`strategies/minervini_volume_dryup/strategy.py:197-217`)는 **`@staticmethod` 이고 `rule_volume_dryup` 만** 본다. **백테스트가 부르는 순수 함수**다.
- `accepts_volume_fallback = False`(`strategy.py:76`, 2026-08-18) 라 스크리너를 안 거친 종목은 안 들어온다.
- ⇒ **재무는 후보 «순위»의 문제이지 매수 «자격»의 문제가 아니다.** 이 경계를 §3-5 가 못박는다.

### 1-3. 재무 원장 두 벌 — 이 설계의 핵심 사실

| 원장 | 최신 `rcept_dt` | 마지막 쓰기 | 리포 안 writer | 연간(11011) 커버리지 |
|---|---|---|---|---|
| `dart_financials_asfiled` (**판정된 `F` 가 쓰는 표**) | 2026-08-06 | **2026-08-08 17:11** | 🔴 **0건** | 2019~2025 ✅ |
| `dart_financial_filings` + `fn_financials_as_of(date)` | 2026-09-08 | 2026-09-10 16:06 | `collectors/financial_writer.py` | 🔴 **2024~2025 뿐** |

- 신 원장의 PIT 함수는 `collectors/financial_metrics.py:100-134`(`fn_financials_as_of`)이고 `rcept_dt <= p_as_of` 필터가 **함수 안**에 있다. `collectors/financial_writer.py:3` 은 구 원장을 **「죽었다」**고 명시한다(*키가 «기간»이라 정정공시가 원본을 덮어쓴다*).
- 🔴 ⇒ ***B-1a(수집기 완료)가 「배선해도 안 썩는다」를 뜻하지 않는다.*** 수집기는 **다른 표**를 채운다. 겹치는 구간 `F` 일치율은 **98.2%**(as_of 2026-09-10 · 공통 493 · 구 원장에만 9 · 신 원장에만 0).

---

## 2. 설계 질문 판정

### Q1. 재무 읽기 경로 — **채택: `resolve_financial_source_db()` 신설 (B-1b)**

`config/constants.py:327-366` 의 resolver 는 `daily`/`minute`/`corp_events` **셋뿐**이고, 같은 파일 `:317-322` 가 *「재무는 `QUANT_FINANCIAL_DB` 로 **독립 제어**한다 — 가격과 재무가 분리돼 있는 것이 의도된 설계」*라고 적어 두었다. 유일한 구현은 `multiverse/data/pit_reader.py:107` 인데 **연구 디렉토리**이고 대상 표가 `quant_financial_ratio` 계열이라 재사용 불가.

```python
# config/constants.py — 위 세 resolver 와 «같은 형식» (읽기 전용 · 재무 원장 단일 진입점)
def resolve_financial_source_db() -> str:
    return _os.getenv("QUANT_FINANCIAL_DB", _KIS_TEMPLATE_DB) or _KIS_TEMPLATE_DB
```

- 🔑 **`QUANT_FINANCIAL_DB` 를 «유지»한다** — 폐기된 가격 스위치(`KIS_DATA_SOURCE` 등)와 성격이 다르다. 이 override 는 **이관 원본 대조**에 쓰이고 `tests/test_research_data_source.py:248-255` 가 존재를 회귀 고정한다.
- 🔴 **fail-fast(`require_explicit_target_db`, `:369`)는 «쓰기»에만** 붙인다. 이 경로는 **읽기 전용**이라 resolver 를 쓴다 — 읽기가 `TIMESCALE_DB` 를 요구하면 워크트리·CI 에서 죽는다.
- ⚠️ **resolver 는 DB명만 돌려준다.** 「어느 «표»를 읽는가」는 Q2 가 **따로** 정한다 — ***DB명만 한 곳에 모으고 표 선택을 흩뿌리면 §1-3 의 「동결된 원장」을 조용히 읽게 된다.***

### Q2. 소스 원장 — **채택: 구 원장(`dart_financials_asfiled`) + «신선도 계기»**

| 안 | 평가 |
|---|---|
| (i) 신 원장 `fn_financials_as_of()` | 🟢 매일 갱신 · PK 가 접수건이라 덮어쓰기가 구조적으로 불가 · 🔴 **연간이 2024~2025 뿐이라 백테스트 창(2024-03~2026-05)을 못 덮는다** ⇒ 사전등록과 라이브가 «다른 함수»가 된다 |
| **(ii) 구 원장 (채택)** | ✅ **판정된 `F` 와 «같은 표»** ⇒ 자문 §7-1(판정된 형태로 배선) 이행 · 🔴 **2026-08-08 이후 갱신 없음** |
| (iii) 즉시 전환 + 2019~2023 백필 | 원리적으로 옳지만 **범위 폭발**(백필 = 별도 과제) · 전환 자체가 새 축 |

**채택 (ii)** 하되 🔴 **동결된 원장을 조용히 읽지 않게 만든다** — 계기 줄에 `src=asfiled` 와 **`src_max_rcept`**(그 표의 최신 접수일)를 **매일** 찍는다(§3-3). 사전등록 §4-4 관문 **S2** 가 *「관측 창 안에서 `src_max_rcept` 가 한 번이라도 전진하지 않으면 발효 보류」*를 사전 고정한다.

🔑 ***「수집기가 생겼다」와 「내가 읽는 표가 갱신된다」는 다른 명제다.*** 원래 경고(B-1a: *수집기 없이 배선하면 사업연도가 고정된 채 조용히 썩는다*)는 **살아 있고 원인만 바뀌었다.** **부수 결정**: 두 원장의 `F` 차분(오늘 98.2%)은 백테스트 1단계 게이트 **G6** 에서 재고 **원장 전환은 별도 문서**로 둔다.

### Q3. 배선 층 — **채택: `build_context()` 조회 + `match()` 계수 + `finalize_scan()` 인쇄 · `scan()` 경로 «한정»**

| 층 | 평가 |
|---|---|
| A. `base_filter()` | 🔴🔴 **금지.** RS 분모가 384 → 112 로 바뀌어 **TT 판정이 오염된다**(§1-1) |
| **B. `build_context()` (채택 · 조회)** | 2패스 훅이 이미 있고(`_rule_screener_base.py:112-125`) 그날 유니버스를 한 번에 받는다 ⇒ **스캔당 SQL 1회** · 종목별 루프 안 384회 조회를 회피 |
| **B2. `match()` (채택 · 계수)** | `ctx` 에서 `f_flag` 를 읽어 tally 만 올린다. **반환값은 손대지 않는다** |
| **B3. `finalize_scan()` (채택 · 인쇄)** | `TT게이트` 줄 옆에 `[fund-rank]` 1줄 |
| C. `_rule_screener_base.scan()` 정렬 키 훅 | 정렬은 base 의 책임이라 **발효 때는 여기가 맞다.** 🔴 그러나 **8전략 공통 경로**라 9/22 오염 위험이 shadow 배선보다 크다 ⇒ **이번 범위 밖**(Q4) |
| D. `evaluate_entry()` | 🔴 **금지.** 백테스트가 부르는 순수 함수다(`strategy.py:197-217`). 여기 넣으면 **연구 재현이 조용히 바뀐다** |

🔴 **`scan()` 경로 한정 (rs_leader errata E1 승계).** 연구 러너들이 어댑터를 «직접» 만들어 쓴다 — `backtest/concept_axes/minervini/run.py:895,1371,1507,1893` · `backtest/rank_score_counterfactual/run.py:64-65,145` · `backtest/concept_axes/minervini/tt_counterfactual/run_ledger.py:175` · `verify_live_wiring.py:58`. ⇒ `scan()` override 가 `_fr_active` 를 세우고 `build_context`/`match` 첫 줄이 `mode == "off" or not _fr_active` 면 **이전 경로로 그대로 돌아간다.**
⚠️ **`attrs` 유무로 가르는 대안 금지** — 러너가 언젠가 붙이면 조용히 켜진다(폴백이 고장을 감추는 형태).

### Q4. `on` 모드 — **채택: 상수에 «등재»하되 이번 구현 범위 «밖». 설정 시 WARNING + `shadow` 강등**

| 안 | 평가 |
|---|---|
| (a) 3모드 전부 구현(rs_leader 선례) | 🟢 발효가 **상수 한 글자** · 🔴 정렬 배선이 **8전략 공통 경로**(Q3-C)를 건드려 9/22 오염 위험 · 🔴 10/19 에 「발효 안 함」이 나오면 **쓰이지 않는 코드**가 남는다(죽은 가드 계열) |
| **(b) off/shadow 만 구현 (채택)** | ✅ 바뀌는 파일이 minervini 패키지 «안»에 갇힌다 · ✅ 「한 번에 한 축만」 · 🔴 **대가: 발효가 한 글자가 아니라 새 PR 이 된다** |

**채택 (b).** 결정적 근거는 **자문 §7-1** — *판정된 조합이 아닌 형태로 배선하지 말 것*. **10/19 시점에 사전등록 §2 백테스트 판정문이 무엇으로 나올지 아직 모른다.** 판정 «전»에 정렬 코드를 얹어 두면 「스위치만 켜면 되는 상태」가 판정을 압박한다. 🔴 **이 비대칭(rs_leader 는 3모드 전부 구현했다)을 §6-4 사장님 결정 항목으로 올린다.**

### Q5. 계기 로그 — §3-3. **칸 정의가 모드에 걸리지 않게** 한다(rs_leader errata E3 승계)

### Q6. RS 와의 비결합 — **채택: `build_context` 안에서 «두 개의 독립 try»**

🔴 현행 `build_context` 는 실패 시 **`{}` 를 조기 반환**한다(`screener.py:107-110` 유니버스 <2 · `:117-121` 예외). 재무 조회를 같은 블록에 넣으면 **RS 가 죽을 때 재무도 같이 사라지고 그 반대도 성립**한다 ⇒ ***폴백이 「없다」와 「고장」을 같이 처리하면 고장을 감춘다.***
**두 산출을 독립 try 로 분리**하고 `ctxs` 를 **RS 성공 종목이 아니라 «프레임이 있는 종목 전체»**로 만든다(현행은 `rs_value` 가 NaN 인 종목을 `:123-126` 에서 스킵하므로, 그대로 두면 그 종목의 `f_flag` 가 사라진다).

### Q7. 범위 밖으로 «명시»하는 것

1. **정렬을 실제로 바꾸는 것**(= `on`, Q4) · **`evaluate_entry` · `_check_buy` · `_check_sell` · `evaluate_sell_conditions` · `position_monitor`** — 한 줄도 안 건드린다.
2. **`base_filter` · `TT_FILTER_MODE` · `_TT_LOOKBACK`(260) · `sanity_window`(90) · `score` 정의** · **다른 7전략** · `_rule_screener_base.py` · `core/` · `bot/` · `collectors/` · `screener_snapshots` 스키마.
3. **원장 전환**(구 → 신) · **문턱 +25% 재설정** · **분기 재무 전환** — 각각 별도 사전등록.

---

## 3. 채택 설계

### 3-1. 데이터 흐름

```
[스크리너 09:00, scan_date=D-1]  Adapter.scan (override, screener.py:215)
   _reset_counters() + (신설) _fr_active=True · _fr_mode 확정  →  RuleScreenerBase.scan
     base_filter(384) → _prepare_frame(260봉 + 불가능봉 가드 90봉, 기존)
     → build_context(frames, scan_date)
          ├─ [기존] RS 백분위                        ← try A (독립)
          └─ [신설] F 맵 «스캔당 1회» 조회             ← try B (독립)
               mode=off 또는 not _fr_active 면 호출 «0»
     → match(df, params, ctx)
          ├─ [기존] dryup → TT → (score, reason)     ← «반환값 불변»
          └─ [신설] ctx[f_flag] 로 tally 만 증가       ← 후보에 영향 0
     → 정렬 + topK (기존 그대로 · score 내림차순)
   → finalize_scan: [기존] TT게이트 1줄 + [신설] [fund-rank] 1줄

[후보 소비 09:00 · 장중 on_tick]   «한 줄도 안 바뀐다»
```

🔑 `reorder_topK` 는 `finalize_scan` 에서 **«가상으로»** 계산한다 — `(f_flag, score)` 로 다시 정렬해 상위 K 를 뽑고
현행 상위 K 와 집합 차분을 낸다. **실제 반환값은 건드리지 않는다.** `K` 는 `config.yaml` `max_positions`(현재 3)를
**어댑터 파라미터로 주입**한다 — 스크리너가 전략 config 를 안 읽으므로 **상수로 재선언하면 문턱 이중선언**이 된다.

### 3-2. 상수 — 1개 (3모드) · 기본 `off`

```python
# config/constants.py  (rs_leader `:257-289` · 섹터 뉴스 `:229-249` 와 «같은 형식»)
#   off    : 판정 자체를 안 한다 (DB 접근 0 · 로그 0)   ← 기본값 · 롤백 위치
#   shadow : 조회·기록만, 후보·순서는 «원래대로»        ← 9/29 전환 목표
#   on     : 순위 발효  🔴 이번 범위 «밖» — 설정하면 WARNING + shadow 강등 (§2 Q4)
MINERVINI_FUND_RANK_MODES = ("off", "shadow", "on")
def resolve_minervini_fund_rank_mode(raw):  # 비어 있으면 off · 모르는 값이면 off + 원문
```

🔴 **기본값이 `off` 인 이유**(rs_leader·섹터 뉴스는 `shadow` 기본이라 «다르다» — 의도적): 머지가 **9/22 TT 판정
«뒤», 9/29 전환 «전»**에 일어난다. 그 사이에는 ***minervini 스캔 경로에서 이 코드가 한 줄도 돌지 않는 상태***라야
TT 관측·C1 반사실 원장이 오염되지 않는다. 모르는 값을 `off` 로 낮추되 원문을 돌려주는 규약은
`resolve_sector_news_mode`(`config/constants.py:238-245`) 선례 그대로.

### 3-3. 계기 로그 (태그 고정 — 발효일을 끊는다)

```
[fund-rank] mode=shadow (startup)
[fund-rank] mode=shadow scan_date=2026-09-29 universe=384 evaluated=380 matched=5 with_f=3 f0=2 null=0 src=asfiled src_max_rcept=2026-08-06 K=3 reorder_topK=1 in=005930 out=000660 old=A,B,C,D,E new=C,A,E,B,D
```

- `matched`·`with_f`·`f0`·`null` 은 **모드에 안 걸린다**(errata E3 승계). `with_f + f0 + null == matched` 가 **불변식**이다.
- **세 칸을 따로 찍는 이유**: 접으면 「배관 고장」이 「그냥 `F` 통과 0건」처럼 보인다 — ***한 규칙의 두 축은 따로 판정한다***(09-08 교훈).
- `src_max_rcept` = **원장 신선도**. 며칠째 그대로면 그 자체가 경보다(§2 Q2).
- **기동 줄**이 필요한 이유: 스캔 줄은 `SCREENER_SNAPSHOT_ENABLED`(`config/constants.py:225`, 기본 `false`)가 꺼지면 통째로 사라진다 ⇒ 실패 조건은 **「기동 줄은 있는데 스캔 줄이 없는 날」**로 읽는다(errata E4 승계).
- 🔴 `screener_snapshots` 로는 관측 불가 — DDL 에 `reason` 이 없고 INSERT 가 `metadata=None`(`db/repositories/candidate.py:134` · README 「TT 승격 체크리스트」 ③). **계기는 로그다.**

### 3-4. 롤백

`MINERVINI_FUND_RANK_MODE` 를 **`"off"`**(또는 env 삭제)로. **그것 하나뿐이다.**
⚠️ 이번 범위에서는 **shadow 조차 후보를 안 바꾸므로 롤백해도 매매 거동 차이가 0**이다 — 되돌리는 것은 로그와 DB 조회 1회뿐.

### 3-5. 바꾸면 «안 되는» 것

1. `evaluate_entry`(`strategy.py:197-217`) — **백테스트가 부르는 순수 함수**. 재무를 넣으면 연구 재현이 조용히 바뀐다.
2. `_check_buy`(`:280-320`) · `_check_sell`(`:322-361`) · `evaluate_sell_conditions`(`:219-252`) · `core/trading/position_monitor.py`.
3. `base_filter`(`screener.py:84-94`) · `build_context` 의 **RS 분모 정의**(`:102-104`) · `TT_FILTER_MODE`(`:42`) · `_TT_LOOKBACK`(260) · `sanity_window`(90).
4. `_rule_screener_base.py` 의 `scan`/`_prepare_frame`/정렬 계약 · 다른 7전략 · `core/` · `bot/` · `collectors/`.
5. `screener_snapshots` 스키마 · 저장되는 `score` 값 · `MAX_CANDIDATES_PER_STRATEGY`(20) · `max_per_strategy`(10).

---

## 4. 테스트 계약 (TDD — 전부 «먼저» 실패해야 한다)

| # | 계약 |
|---|---|
| **T1** | 🔴 **`mode=off` 회귀 게이트** — 합성 유니버스로 `scan()` → 후보 **코드·순서·`score` 가 변경 «전»과 완전 일치**, 그리고 **재무 리더 호출 0회** |
| T2 | `mode=shadow` → `scan()` 반환이 **T1 과 동일** + `[fund-rank]` 줄 1개 |
| T3 | **NULL 3종**(재무 행 없음 / `operating_income` NULL / 전년 미가시) → 각각 `null` 칸에 계상 · `with_f+f0+null == matched` |
| **T4** | 🔴 **PIT 경계** — `rcept_dt == scan_date` 는 **안 보이고**(≤ D−1), `rcept_dt == scan_date − 1` 은 **보인다**(대칭 단언) |
| **T5** | 🔴 **수량사** — 「가장 최근 가시 연도 «하나»」만 판정. 과거에 +25% 한 해가 있어도 **최근 해가 미달이면 `F=0`**(문서 1 §10-2) |
| T6 | `prev_oi <= 0` → `F=0` (적자→흑자 전환이 무한대 성장률로 통과하지 않는다) |
| **T7** | 🔴 **RS 와 비결합(대칭)** — ①재무 조회가 예외를 던져도 RS·후보 **불변** ②RS 산출이 실패해도 `[fund-rank]` 줄은 **난다** |
| T8 | `rs_value` 가 NaN 인 종목도 `f_flag` 를 **받는다**(`screener.py:123-126` 스킵에 딸려가지 않는다) |
| **T9** | 🔴 **`scan()` 밖에서 `match()`/`build_context()` 직접 호출** → 원래 튜플 + **재무 조회 0회** + 카운터 무오염. 그리고 «같은» 프레임이 `scan()` 안에서는 계수된다(대칭 단언 · errata E1) |
| T10 | `mode="on"` → **WARNING + shadow 강등** · 후보·순서 불변 (§2 Q4) · `"banana"` → `off` + WARNING |
| T11 | **`evaluate_entry` 불변(대칭)** — `F=0` 종목 프레임으로도 dryup 만 보고 **매수 신호가 그대로 난다** |
| T12 | 다른 7전략 어댑터에 같은 유니버스 → 후보 집합·순서 **불변**(`assert base is not None` 먼저 — 공허한 통과 금지) |
| T13 | `reorder_topK`·`in=`·`out=` 이 `(f_flag, score)` 재정렬과 일치 · **`K` 는 주입값**(리터럴 3 없음) |
| T14 | `resolve_financial_source_db()` — 기본 `kis_template` · `QUANT_FINANCIAL_DB` override 동작 · **가격 resolver 와 비결합** |

**리포지토리 회귀 게이트**: 워크트리에서만 · **09:10 KST 이후** · 기준선 `D:/tmp/main_baseline_failures_20260907.txt` 와
실패 **집합의 양방향 차분**(새로 생긴 것 / 사라진 것 둘 다 0). 🔴 **라이브 트리에서 테스트 실행 금지.**

---

## 5. 구현 계획 개요 · 사전등록 연결

- 워크트리 `D:/tmp/kis-wt-minervini-fundrank` · 브랜치 `feat/minervini-fund-rank-shadow` · base = **9/22 판정 «후» main**.
- 커밋 단위: ① `test:` T1~T14(red) → ② `feat:` `resolve_financial_source_db()` + `db/financial_pit_reader.py`(신설)
  → ③ `feat:` 3모드 상수 + resolver → ④ `feat:` `build_context` F 맵 + `match` 계수
  → ⑤ `feat:` `finalize_scan` 계기 줄 + 기동 줄 → ⑥ `docs:` README 「F_shadow 관측 체크리스트」 + `SHADOW_LOG_FUND.md` 빈 표.
- 예상 변경 **5파일**: `config/constants.py` · `db/financial_pit_reader.py`(신설) · `strategies/minervini_volume_dryup/screener.py` ·
  README · 테스트 1~2파일. 🔴 **`_rule_screener_base.py` · `strategy.py` · `core/` · `bot/` · `collectors/` 는 안 건드린다.**
- 순서: 구현 → `code-reviewer` → 사장님 보고 → **머지(9/22 판정 뒤 · 장중 밖 · `--no-ff`)** → **9/29 `shadow` 전환(별도 승인)**.
- **사전등록 연결**: 이 로그가 곧 `PREREG_FUNDAMENTAL_RANK.md` §4 의 입력이다. 관문 **S1 배관**(`null/matched`) ·
  **S2 신선도**(`src_max_rcept`) · **S3 노출**(`reorder_topK`)이 전부 이 줄에서 나온다. **S4 검정**은 §2 백테스트가 답한다.
  🔴 **shadow 성적으로 발효를 정하지 않는다**(자문 §7-2).

---

## 6. 미확인 · 후속

1. 🔴 **`dart_financials_asfiled` 가 왜 2026-08-08 이후 갱신되지 않는가** — writer 를 리포에서 찾지 못했다
   (백필 스크립트가 리포 «밖»이었을 가능성). **S2 가 보류를 걸기 «전»에 규명하는 편이 낫다.**
2. **원장 전환(구 → 신)** — 2019~2023 연간 백필이 선행. 별도 설계·별도 사전등록.
3. **`on` 구현(정렬 키 훅)** — 층 C(`_rule_screener_base.scan`)가 맞고, rs_leader 스펙 §7-2 의 층 A′ 판단과 **같은 계열**이다.
   10/19 발효 결정 뒤 새 설계.
4. 🔒 **사장님 결정 대기**: ① `on` 을 이번에 같이 구현할 것인가(§2 Q4 — rs_leader 선례와의 비대칭)
   ② 기본값 `off` vs `shadow`(§3-2) ③ 머지를 9/22 «직후»로 볼 것인가 9/29 에 붙일 것인가.
5. **미확인** — 이 설계는 「무엇이 바뀌었을지 기록한다」일 뿐 **아무것도 바꾸지 않는다.** 근본 트랙
   (문턱 +25% 대리변수 · 분기 재무 · 컷 축 후보 고갈)은 그대로 남는다.
