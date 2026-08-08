# 재무 리스크 배제필터 — Phase 2A: 패널 구축 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관측 단위 `(종목, 날짜)` 로 **폭락 타겟**과 **그날 알 수 있었던 재무 피처**를 결합한 패널을 만들고, **플래그 비율을 실측해 Phase 2B 가 검정 가능한지 판정**한다.

**Architecture:** 세 단계. `p1_target` 이 SQL 윈도우로 전방 60거래일 폭락 타겟을 뽑고, `p2_features` 가 종목별 **계단 함수**(재무는 연 1회만 바뀐다)를 `pit_join.asof_financials` 로 만들어 `merge_asof` 로 붙이고, `p3_panel` 이 둘을 결합해 진단 리포트를 낸다. 산출물은 parquet 이며 **DB 쓰기는 0** 이다.

**Tech Stack:** Python 3.9.13 · pandas 2.2.3 · numpy 2.0.2 · pyarrow 21.0.0 · psycopg2 (SELECT only) · PostgreSQL 16 @ `127.0.0.1:5433` / `kis_template`

**설계 문서:** [`../specs/2026-08-08-fundamental-risk-filter-design.md`](../specs/2026-08-08-fundamental-risk-filter-design.md) §1(타겟)·§3(필터 축)
**선행:** Phase 1 완료 — `dart_financials_asfiled` **17,892행 / 2,556종목 / FY2019~2025** 적재됨

## Global Constraints

- 🔴 **라이브 코드 수정 0.** `core/ bot/ framework/ api/ strategies/ collectors/ db/ runners/ signals/ utils/ tools/` 무접촉. 신규는 `scripts/discovery/fundamental_risk_filter/` 아래.
- 🔴 **이 Phase 는 DB 에 «쓰지 않는다».** `db_conn()`(read-only)만 쓴다. 산출물은 `scratchpad/fund_pit/*.parquet`.
- 🔴 **DART 호출 0건.** 외부 네트워크 접근 없음.
- 🔴 **as-of 조인 로직을 «재구현하지 말 것».** 반드시 `pit_join.asof_financials` 를 호출한다. 두 벌이 되면 안전장치가 갈라진다.
- 🔴 **임계값을 코드에 넣지 말 것.** 이 Phase 는 **연속값**(부채비율·이자보상배율 등)까지만 만든다. 이진 플래그의 문턱은 Phase 2B 의 `PREREG.md` 에서 동결한다. 유일한 예외는 **자본잠식(`total_equity <= 0`)** 으로, 자유모수가 없다.
  🔑 **진단 리포트에도 후보 문턱을 찍지 않는다.** 분포는 **분위수**로, 블록 수 진단은 **분위수 기반 꼬리 마스크**로 보여준다. 리포트에 `부채비율 > 4배` 같은 값이 한 번 찍히면 그걸 읽은 사람이 그 값에 끌리고, 그게 곧 사후 선택이다.
- 🔴 **결측은 `NaN`/`None`. `0` 으로 채우지 말 것.**
- **타겟 창**: `2021-01-04` ~ **`2026-05-12`**(전방 60거래일이 완결되는 마지막 날, 실측). 그 이후는 절단이라 제외.
- **의사티커 제외**: `KOSPI`·`KOSDAQ`·`KS11`·`KQ11`.
- ⚠️ **`daily_prices.date` 는 TEXT 컬럼**이다. `extract()`·date 비교가 실패한다 — 문자열로 비교할 것.
- ⚠️ **`adj_factor` 를 곱하지 말 것.** `close` 는 이미 분할조정된 연속시세다.
- 라이브 트리에서 pytest 금지. `python -m pytest tests/discovery/fundamental_risk_filter/ -v` 로 한정.
- git commit·push 는 사장님 확인 필요(현 브랜치 `feat/fundamental-risk-filter-pit` 는 일괄 승인됨).

---

## File Structure

| 파일 | 책임 |
|---|---|
| `scripts/discovery/fundamental_risk_filter/p1_target.py` | 전방 60거래일 폭락 타겟 산출 → `frf_target.parquet` |
| `.../p2_features.py` | 종목별 재무 계단함수(`asof_financials` 재사용) + 연속 피처 → `frf_features.parquet` |
| `.../p3_panel.py` | 타겟 ⊕ 피처 결합 + **플래그 비율 진단 리포트** → `frf_panel.parquet`, `frf_panel_report.txt` |
| `tests/discovery/fundamental_risk_filter/test_target.py` | 윈도우 경계·부분창 판정 |
| `.../test_features.py` | 계단함수·look-ahead·연속손실 카운트 |
| `.../test_panel.py` | 결합 정합·진단 계산 |

**실측 기준선(회귀 앵커)** — 2026-08-08 관리자 실측, Task 1 이 이 값을 재현해야 한다:

| 연도 | 60일내 −30% 비율 |
|---|--:|
| 2021 | 6.97% |
| 2022 | 13.11% |
| 2023 | 7.08% |
| 2024 | 12.25% |
| 2025 | 5.92% |

패널 규모(실측): 창 내 관측 **2,975,887** · 종목 **2,596** · 그중 재무 보유 **2,544(98.0%)**

---

## Task 1: 폭락 타겟 산출

**Files:**
- Create: `scripts/discovery/fundamental_risk_filter/p1_target.py`
- Test: `tests/discovery/fundamental_risk_filter/test_target.py`

**Interfaces:**
- Consumes: `dart_client.OUT_DIR`, `dart_client.db_conn`
- Produces:
  - `TARGET_PARQUET: str` (= `<OUT_DIR>/frf_target.parquet`)
  - `WINDOW = 60`, `DROP = -0.30`, `DATE_MIN = "2021-01-04"`, `DATE_MAX = "2026-05-12"`
  - `TARGET_SQL: str`
  - `crash_flags(df: pd.DataFrame) -> pd.DataFrame` — 입력 컬럼 `stock_code, date, close, fwd_min, fwd_n`; 출력에 `ret_min`(float, NaN 허용)·`crash`(bool)·`window_full`(bool) 추가

**왜 `fwd_n` 이 필요한가:** SQL 의 `ROWS BETWEEN 1 FOLLOWING AND 60 FOLLOWING` 은 종목 이력 끝에서 **부분 창**을 준다(상장폐지·수집중단 종목). 전체 데이터 끝(2026-05-12 컷)과는 **별개의 절단**이다.

🔴 **2026-08-08 실측이 초판의 근거를 반증했다.** 초판은 *「부분 창은 폭락률을 과소 측정한다」* 고 적었는데 **반대다**:

| 연도 | 부분 창 | **부분 창 폭락률** | 완결 폭락률 |
|---|--:|--:|--:|
| 2023 | 209 | 0.00% | 7.08% |
| 2024 | 1,732 | **33.26%** | 12.19% |
| 2025 | 193 | **36.79%** | 5.91% |
| 2026 | 909 | **67.00%** | 27.92% |

부분 창은 종목 이력 끝에 몰려 있고 그 자리는 **상장폐지·거래정지 직전**이라 실제로 폭락 중이다. ⇒ 배제 이유는 **「과소 측정이라서」가 아니라 「창 길이가 다른 처치를 받았고 하필 상장폐지에 선택적으로 몰려 있어 창 길이와 결과가 교란되기 때문」**이다. 배제 자체는 옳고, 이유만 틀렸다.

🔑 이 표가 회귀 앵커의 델타도 설명한다 — 2024 는 0.302% 관측을 빼는데 그 폭락률이 33.26%(기저 12.2% 대비 +21%p)라 `(0.1225 − 0.00302×0.3326)/0.99698 = 0.1219`, 관측된 **−0.064%p** 와 정확히 일치한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/discovery/fundamental_risk_filter/test_target.py
import os
import sys

import pandas as pd

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import p1_target as p1  # noqa: E402


def _df(rows):
    return pd.DataFrame(rows, columns=["stock_code", "date", "close",
                                       "fwd_min", "fwd_n"])


def test_constants_match_the_measured_window():
    assert p1.WINDOW == 60
    assert p1.DROP == -0.30
    assert p1.DATE_MIN == "2021-01-04"
    assert p1.DATE_MAX == "2026-05-12"


def test_exactly_minus_30_percent_counts_as_crash():
    """경계는 포함이다 — 정확히 −30% 는 폭락으로 센다."""
    out = p1.crash_flags(_df([("005930", "2022-01-03", 1000.0, 700.0, 60)]))
    assert out["ret_min"].iloc[0] == -0.30
    assert bool(out["crash"].iloc[0]) is True


def test_just_above_threshold_is_not_a_crash():
    out = p1.crash_flags(_df([("005930", "2022-01-03", 1000.0, 700.1, 60)]))
    assert bool(out["crash"].iloc[0]) is False


def test_partial_window_is_flagged_not_dropped():
    """🔴 부분 창은 폭락률을 과소 측정한다. 버리지 말고 «표시»해서 하류가 고르게 한다."""
    out = p1.crash_flags(_df([("005930", "2026-05-11", 1000.0, 900.0, 17)]))
    assert bool(out["window_full"].iloc[0]) is False
    assert bool(out["crash"].iloc[0]) is False   # 값 자체는 계산한다


def test_full_window_is_flagged_full():
    out = p1.crash_flags(_df([("005930", "2022-01-03", 1000.0, 900.0, 60)]))
    assert bool(out["window_full"].iloc[0]) is True


def test_missing_forward_min_yields_nan_not_zero():
    """🔴 결측을 0 으로 만들면 −100% 폭락으로 둔갑한다."""
    out = p1.crash_flags(_df([("005930", "2026-05-12", 1000.0, None, 0)]))
    assert pd.isna(out["ret_min"].iloc[0])
    assert bool(out["crash"].iloc[0]) is False


def test_zero_close_yields_nan_not_division_error():
    out = p1.crash_flags(_df([("005930", "2022-01-03", 0.0, 700.0, 60)]))
    assert pd.isna(out["ret_min"].iloc[0])
    assert bool(out["crash"].iloc[0]) is False


def test_sql_excludes_pseudo_tickers_and_computes_window_size():
    """SQL 이 의사티커를 빼고 창 «크기»도 함께 세는지 문자열 수준에서 고정한다."""
    for t in ("KOSPI", "KOSDAQ", "KS11", "KQ11"):
        assert t in p1.TARGET_SQL
    assert "ROWS BETWEEN 1 FOLLOWING AND 60 FOLLOWING" in p1.TARGET_SQL
    assert "count(" in p1.TARGET_SQL.lower()      # fwd_n 산출
    assert "adj_factor" not in p1.TARGET_SQL      # 곱하지 않는다
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_target.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'p1_target'`

- [ ] **Step 3: 최소 구현을 쓴다**

```python
# scripts/discovery/fundamental_risk_filter/p1_target.py
"""P(1) 폭락 타겟 산출 — 전방 60거래일 최저 종가가 −30% 이하인가.

읽기 전용. DB 쓰기 0 · DART 호출 0.

🔴 윈도우는 «전체 이력»에서 계산한 뒤 타겟 창으로 자른다. 먼저 자르면
   창 끝 근처 관측의 전방 60일이 사라진다.
🔴 부분 창(fwd_n < 60)은 폭락률을 과소 측정하므로 «표시»한다. 버리지 않는 이유는
   어느 관측이 왜 빠졌는지가 기록이어야 하기 때문이다.
⚠️ `daily_prices.date` 는 TEXT 다. 문자열로 비교한다.
⚠️ `adj_factor` 를 곱하지 않는다 — close 는 이미 분할조정 연속시세다.

usage:
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/p1_target.py
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_client import OUT_DIR, db_conn  # noqa: E402

WINDOW = 60
DROP = -0.30
DATE_MIN = "2021-01-04"
DATE_MAX = "2026-05-12"

TARGET_PARQUET = os.path.join(OUT_DIR, "frf_target.parquet")

TARGET_SQL = f"""
WITH px AS (
  SELECT stock_code, date, close,
         MIN(close) OVER (PARTITION BY stock_code ORDER BY date
                          ROWS BETWEEN 1 FOLLOWING AND {WINDOW} FOLLOWING) AS fwd_min,
         count(close) OVER (PARTITION BY stock_code ORDER BY date
                            ROWS BETWEEN 1 FOLLOWING AND {WINDOW} FOLLOWING) AS fwd_n
  FROM daily_prices
  WHERE stock_code NOT IN ('KOSPI','KOSDAQ','KS11','KQ11')
    AND close > 0
)
SELECT stock_code, date, close, fwd_min, fwd_n
FROM px
WHERE date >= %s AND date <= %s
"""


def crash_flags(df):
    """ret_min·crash·window_full 을 붙인다. 결측은 NaN/False (0 으로 채우지 않는다)."""
    out = df.copy()
    close = pd.to_numeric(out["close"], errors="coerce")
    fwd = pd.to_numeric(out["fwd_min"], errors="coerce")
    close = close.where(close > 0)
    out["ret_min"] = fwd / close - 1.0
    out["crash"] = out["ret_min"].le(DROP).fillna(False)
    out["window_full"] = pd.to_numeric(out["fwd_n"], errors="coerce").eq(WINDOW)
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = db_conn()
    df = pd.read_sql(TARGET_SQL, conn, params=(DATE_MIN, DATE_MAX))
    conn.close()

    df = crash_flags(df)
    df.to_parquet(TARGET_PARQUET, index=False)

    full = df[df["window_full"]]
    yr = full.assign(y=full["date"].str[:4]).groupby("y")["crash"].agg(["size", "mean"])
    print(f"관측 {len(df):,} · 종목 {df['stock_code'].nunique():,} "
          f"· 창 완결 {len(full):,} ({100*len(full)/len(df):.2f}%)")
    print()
    print("연도별 폭락률 (창 완결분만):")
    for y, row in yr.iterrows():
        print(f"  {y}  n={int(row['size']):>9,}  {100*row['mean']:6.2f}%")
    print()
    print("🔑 2021~2025 는 관리자 실측(6.97 / 13.11 / 7.08 / 12.25 / 5.92)과")
    print("   ±0.15%p 안에서 일치해야 한다. 벗어나면 창 정의가 어긋난 것이다.")
    print(f"→ {TARGET_PARQUET}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_target.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: 실제로 돌려 회귀 앵커와 대조한다**

Run: `PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/p1_target.py`

**판정 기준 — 반드시 대조하고 보고할 것:**
- 2021~2025 연도별 폭락률이 **6.97 / 13.11 / 7.08 / 12.25 / 5.92 (%)** 와 **±0.15%p** 안에서 일치해야 한다.
- 🔴 **벗어나면 멈추고 보고한다.** 창 정의·필터·정렬 중 하나가 어긋난 것이고, 그대로 진행하면 이후 전부가 틀린 타겟 위에 선다.
- 관측 수는 **2,975,887** 근처여야 한다(±1%).

- [ ] **Step 6: 커밋**

```bash
git add scripts/discovery/fundamental_risk_filter/p1_target.py tests/discovery/fundamental_risk_filter/test_target.py
git commit -m "feat(frf): 폭락 타겟 산출 — 부분 창을 버리지 않고 표시한다"
```

---

## Task 2: PIT 재무 피처

**Files:**
- Create: `scripts/discovery/fundamental_risk_filter/p2_features.py`
- Test: `tests/discovery/fundamental_risk_filter/test_features.py`

**Interfaces:**
- Consumes: `pit_join.asof_financials`, `dart_client.OUT_DIR`, `dart_client.db_conn`
- Produces:
  - `FEATURES_PARQUET: str` (= `<OUT_DIR>/frf_features.parquet`)
  - `FIN_SQL: str`
  - `step_table(records: list[dict]) -> list[dict]` — 종목 하나의 재무 이력 → **계단 구간** 목록. 각 원소 `{"from_date", "bsns_year", "rcept_dt", "equity_impaired", "debt_ratio", "op_loss_years", "interest_coverage"}`
  - `consec_op_loss(records: list[dict], as_of: str) -> int`

**왜 계단 함수인가:** 재무는 종목당 연 1회만 바뀐다(이력 7행). 3백만 관측마다 as-of 조인을 부르면 낭비다. **접수일 경계마다 한 번씩만** `asof_financials` 를 호출해 계단을 만든 뒤 `merge_asof` 로 붙인다.

🔴 **정렬만으로 계단을 만들면 안 된다.** 접수일 순으로 정렬해 마지막을 취하면 **가장 최근 「문서」**가 뽑히는데, 정정공시 때문에 그것이 **가장 최근 「사업연도」**가 아닐 수 있다(Phase 1 F3 가 정확히 이 버그였다). 그래서 각 경계에서 **`asof_financials` 를 그대로 호출**한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/discovery/fundamental_risk_filter/test_features.py
import os
import sys

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import p2_features as p2  # noqa: E402


def _rec(year, dt, eq=1000, cap=100, li=500, oi=50, fc=10):
    return {"bsns_year": year, "rcept_dt": dt, "total_equity": eq,
            "issued_capital": cap, "total_liabilities": li,
            "operating_income": oi, "finance_costs": fc}


def test_step_boundaries_start_the_day_after_receipt():
    """🔴 접수일 «당일»은 아직 안 보인다(장중 공시 가능). 다음 날부터 적용된다."""
    steps = p2.step_table([_rec("2020", "2021-03-19")])
    assert steps[0]["from_date"] == "2021-03-20"


def test_step_uses_latest_fiscal_year_not_latest_document():
    """🔴 Phase 1 F3 의 재발 방지. 2021년분 정정이 2023년분 원본을 이기면 안 된다."""
    recs = [_rec("2023", "2024-03-20", eq=300),
            _rec("2021", "2024-05-10", eq=100)]
    steps = p2.step_table(recs)
    last = steps[-1]
    assert last["bsns_year"] == "2023"
    assert last["from_date"] == "2024-05-11"   # 경계는 정정 접수 다음날에도 생긴다


def test_equity_impaired_is_the_only_hardcoded_rule():
    steps = p2.step_table([_rec("2020", "2021-03-19", eq=-5)])
    assert steps[0]["equity_impaired"] is True
    steps = p2.step_table([_rec("2020", "2021-03-19", eq=5)])
    assert steps[0]["equity_impaired"] is False


def test_debt_ratio_is_none_when_equity_not_positive():
    """자본이 0 이하면 부채비율은 정의되지 않는다 — 0 이나 inf 로 만들지 않는다."""
    steps = p2.step_table([_rec("2020", "2021-03-19", eq=0, li=500)])
    assert steps[0]["debt_ratio"] is None
    steps = p2.step_table([_rec("2020", "2021-03-19", eq=-1, li=500)])
    assert steps[0]["debt_ratio"] is None


def test_debt_ratio_value():
    steps = p2.step_table([_rec("2020", "2021-03-19", eq=200, li=500)])
    assert abs(steps[0]["debt_ratio"] - 2.5) < 1e-9


def test_interest_coverage_is_none_when_finance_costs_not_positive():
    steps = p2.step_table([_rec("2020", "2021-03-19", oi=50, fc=0)])
    assert steps[0]["interest_coverage"] is None
    steps = p2.step_table([_rec("2020", "2021-03-19", oi=50, fc=None)])
    assert steps[0]["interest_coverage"] is None


def test_interest_coverage_value_allows_negative_numerator():
    """영업손실이면 이자보상배율은 음수다 — 결측이 아니라 «나쁜 값»이다."""
    steps = p2.step_table([_rec("2020", "2021-03-19", oi=-40, fc=10)])
    assert abs(steps[0]["interest_coverage"] - (-4.0)) < 1e-9


def test_consec_op_loss_counts_only_visible_consecutive_years():
    recs = [_rec("2019", "2020-03-30", oi=-1),
            _rec("2020", "2021-03-19", oi=-1),
            _rec("2021", "2022-03-22", oi=5)]
    assert p2.consec_op_loss(recs, "2021-06-30") == 2   # 2019·2020 둘 다 적자
    assert p2.consec_op_loss(recs, "2023-01-01") == 0   # 2021 이 흑자라 끊긴다
    assert p2.consec_op_loss(recs, "2020-01-01") == 0   # 아무것도 안 보인다


def test_consec_op_loss_stops_at_a_missing_year():
    """중간 연도가 결측이면 «연속»이 끊긴다 — 없는 해를 적자로 세지 않는다."""
    recs = [_rec("2019", "2020-03-30", oi=-1),
            _rec("2021", "2022-03-22", oi=-1)]
    assert p2.consec_op_loss(recs, "2023-01-01") == 1


def test_step_table_of_empty_history_is_empty():
    assert p2.step_table([]) == []
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_features.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'p2_features'`

- [ ] **Step 3: 최소 구현을 쓴다**

```python
# scripts/discovery/fundamental_risk_filter/p2_features.py
"""P(2) 그날 알 수 있었던 재무 피처 — 종목별 계단함수 + merge_asof.

읽기 전용. DB 쓰기 0 · DART 호출 0.

🔴 as-of 로직을 재구현하지 않는다. 접수일 경계마다 `pit_join.asof_financials`
   를 «그대로» 호출한다. 정렬해서 마지막을 취하면 가장 최근 「문서」가 뽑히는데,
   정정공시 때문에 그것이 가장 최근 「사업연도」가 아닐 수 있다(Phase 1 F3).
🔴 임계값을 넣지 않는다. 연속값까지만 만들고 문턱은 Phase 2B 의 PREREG 에서 동결한다.
   유일한 예외가 자본잠식(total_equity <= 0)이고, 그건 자유모수가 없다.

usage:
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/p2_features.py
"""
import datetime as _dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_client import OUT_DIR, db_conn  # noqa: E402
from p1_target import DATE_MAX, TARGET_PARQUET  # noqa: E402
from pit_join import asof_financials  # noqa: E402

FEATURES_PARQUET = os.path.join(OUT_DIR, "frf_features.parquet")

FIN_SQL = """
SELECT stock_code, bsns_year, rcept_dt::text, total_equity, issued_capital,
       total_liabilities, operating_income, finance_costs
FROM dart_financials_asfiled
WHERE rcept_dt IS NOT NULL
ORDER BY stock_code, rcept_dt
"""


def _next_day(daystr):
    d = _dt.date(int(daystr[0:4]), int(daystr[5:7]), int(daystr[8:10]))
    return (d + _dt.timedelta(days=1)).isoformat()


def consec_op_loss(records, as_of):
    """as_of 에 보이는 사업연도들을 최신부터 훑어 «연속» 영업손실 연수를 센다.

    중간 연도가 비면 거기서 끊는다 — 없는 해를 적자로 세지 않는다.
    """
    visible = {}
    for r in records:
        cur = asof_financials([r], as_of)
        if cur is None:
            continue
        visible[str(r["bsns_year"])] = r.get("operating_income")
    if not visible:
        return 0
    n = 0
    year = max(int(y) for y in visible)
    while True:
        oi = visible.get(str(year))
        if oi is None or oi >= 0:
            break
        n += 1
        year -= 1
    return n


def _row(rec, records, as_of):
    eq = rec.get("total_equity")
    li = rec.get("total_liabilities")
    oi = rec.get("operating_income")
    fc = rec.get("finance_costs")
    return {
        "from_date": as_of,
        "bsns_year": str(rec["bsns_year"]),
        "rcept_dt": str(rec["rcept_dt"])[:10],
        "equity_impaired": (eq is not None and eq <= 0),
        "debt_ratio": (li / eq) if (eq is not None and eq > 0 and li is not None) else None,
        "op_loss_years": consec_op_loss(records, as_of),
        "interest_coverage": (oi / fc) if (fc is not None and fc > 0 and oi is not None) else None,
    }


def step_table(records):
    """종목 하나의 재무 이력 → 계단 구간 목록(from_date 오름차순)."""
    dates = sorted({str(r["rcept_dt"])[:10] for r in records if r.get("rcept_dt")})
    steps = []
    for d in dates:
        as_of = _next_day(d)          # 접수 «다음 날»부터 보인다
        cur = asof_financials(records, as_of)
        if cur is None:
            continue
        steps.append(_row(cur, records, as_of))
    return steps


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = db_conn()
    fin = pd.read_sql(FIN_SQL, conn)
    conn.close()

    rows = []
    for code, g in fin.groupby("stock_code", sort=True):
        recs = g.to_dict("records")
        for s in step_table(recs):
            s["stock_code"] = code
            rows.append(s)
    steps = pd.DataFrame(rows)
    # 🔴 merge_asof 는 `on` 키가 «전역» 단조여야 한다. by= 를 줘도 마찬가지다.
    #    ["stock_code","from_date"] 로 정렬하면 from_date 가 전역 단조가 아니라
    #    ValueError: left keys must be sorted 로 죽는다. on 키«만»으로 정렬한다.
    steps = steps[steps["from_date"] <= DATE_MAX].sort_values(
        "from_date", kind="mergesort").reset_index(drop=True)

    tgt = pd.read_parquet(TARGET_PARQUET, columns=["stock_code", "date"])
    tgt = tgt.sort_values("date", kind="mergesort").reset_index(drop=True)

    merged = pd.merge_asof(
        tgt, steps,
        left_on="date", right_on="from_date", by="stock_code",
        direction="backward", allow_exact_matches=True,
    )
    merged.to_parquet(FEATURES_PARQUET, index=False)

    have = merged["bsns_year"].notna()
    print(f"계단 구간 {len(steps):,} · 종목 {steps['stock_code'].nunique():,}")
    print(f"패널 관측 {len(merged):,} · 재무 매칭 {have.sum():,} "
          f"({100*have.mean():.2f}%)")
    print(f"  자본잠식        {merged['equity_impaired'].fillna(False).mean()*100:6.3f}%")
    print(f"  부채비율 有     {merged['debt_ratio'].notna().mean()*100:6.2f}%")
    print(f"  이자보상배율 有 {merged['interest_coverage'].notna().mean()*100:6.2f}%")
    print(f"  연속영업손실≥1  {(merged['op_loss_years'].fillna(0) >= 1).mean()*100:6.2f}%")
    print(f"→ {FEATURES_PARQUET}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_features.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: 실제로 돌려 look-ahead 를 실데이터로 재확인한다**

```bash
PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/p2_features.py
```

그리고 look-ahead 를 **전 패널 불변식**으로 확인해 보고한다.

🔴 **초판은 `000040`(KR모터스)의 `2022-05-18/19` 경계를 앵커로 지정했는데 그것은 쓸 수 없다.**
그 종목은 **가격 데이터가 2024-03-13 부터**(525행)라 2022년 관측이 패널에 아예 없다.
Phase 1 의 확인은 `dart_financials_asfiled` **재무 테이블에서 직접** 한 것이고, 재무엔 FY2021 이
있어도 **그 시점 가격이 없으면 패널 행이 생기지 않는다.** ⇒ ***앵커 하나를 지정할 때 그 앵커가
검사 대상 산출물에 실제로 존재하는지 먼저 확인해야 한다.***

대신 **전수 불변식**을 쓴다 — 앵커 하나보다 강하다:

```bash
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python -c "
import pandas as pd, sys
sys.path.insert(0,'scripts/discovery/fundamental_risk_filter')
from p2_features import FEATURES_PARQUET
d = pd.read_parquet(FEATURES_PARQUET, columns=['stock_code','date','bsns_year','rcept_dt'])
m = d[d.bsns_year.notna()].copy()
m['rcept_dt'] = m['rcept_dt'].astype(str).str[:10]
bad = m[m['date'] <= m['rcept_dt']]
print('매칭 행', len(m), ' look-ahead 위반(date <= rcept_dt):', len(bad))
lag = (pd.to_datetime(m['date']) - pd.to_datetime(m['rcept_dt'])).dt.days
print('date - rcept_dt 일수: min', lag.min(), ' p50', int(lag.median()), ' max', lag.max())
"
```

**판정 기준:**
- 🔴 **위반 0건**이어야 한다. 1건이라도 있으면 look-ahead 이고 즉시 중단·보고한다.
- 🔴 **`min` 이 정확히 `1`** 이어야 한다. `0` 이면 접수 당일이 보이는 것(look-ahead), `2` 이상이면
  경계가 하루 늦게 열린 것이다.

**실측(2026-08-08)**: 매칭 2,786,895행 · 위반 **0** · lag min **1** · p50 184 · max 2,185.

- [ ] **Step 6: 커밋**

```bash
git add scripts/discovery/fundamental_risk_filter/p2_features.py tests/discovery/fundamental_risk_filter/test_features.py
git commit -m "feat(frf): PIT 재무 피처 — 계단함수로 as-of 조인을 재사용한다"
```

---

## Task 3: 패널 결합 + 진단 리포트

**Files:**
- Create: `scripts/discovery/fundamental_risk_filter/p3_panel.py`
- Test: `tests/discovery/fundamental_risk_filter/test_panel.py`

**Interfaces:**
- Consumes: `p1_target.TARGET_PARQUET`, `p2_features.FEATURES_PARQUET`
- Produces:
  - `PANEL_PARQUET: str` (= `<OUT_DIR>/frf_panel.parquet`)
  - `REPORT_TXT: str` (= `<OUT_DIR>/frf_panel_report.txt`)
  - `usable(df: pd.DataFrame) -> pd.DataFrame` — 창 완결 ∧ 재무 매칭 관측만
  - `monthly_rates(df: pd.DataFrame) -> pd.DataFrame` — `ym` 별 `n`·`crash_rate`

**이 태스크의 «진짜» 산출물은 진단 리포트다.** Phase 2B 가 검정 가능한지를 여기서 판정한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/discovery/fundamental_risk_filter/test_panel.py
import os
import sys

import pandas as pd

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "scripts", "discovery", "fundamental_risk_filter",
)
sys.path.insert(0, _SCRIPTS)

import p3_panel as p3  # noqa: E402


def _panel(rows):
    return pd.DataFrame(rows, columns=["stock_code", "date", "crash",
                                       "window_full", "bsns_year"])


def test_usable_requires_both_full_window_and_financials():
    df = _panel([
        ("A", "2022-01-03", True, True, "2020"),    # 남는다
        ("B", "2022-01-03", True, False, "2020"),   # 부분 창
        ("C", "2022-01-03", True, True, None),      # 재무 없음
    ])
    out = p3.usable(df)
    assert list(out["stock_code"]) == ["A"]


def test_usable_does_not_mutate_input():
    df = _panel([("A", "2022-01-03", True, True, "2020")])
    before = len(df)
    p3.usable(df)
    assert len(df) == before


def test_monthly_rates_keys_on_year_month():
    df = _panel([
        ("A", "2022-01-03", True, True, "2020"),
        ("B", "2022-01-04", False, True, "2020"),
        ("C", "2022-02-03", True, True, "2020"),
    ])
    r = p3.monthly_rates(p3.usable(df)).set_index("ym")
    assert list(r.index) == ["2022-01", "2022-02"]
    assert r.loc["2022-01", "n"] == 2
    assert abs(r.loc["2022-01", "crash_rate"] - 0.5) < 1e-9
    assert abs(r.loc["2022-02", "crash_rate"] - 1.0) < 1e-9


def test_monthly_rates_on_empty_input_is_empty_not_error():
    r = p3.monthly_rates(_panel([]).assign(crash=[]))
    assert len(r) == 0
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_panel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'p3_panel'`

- [ ] **Step 3: 최소 구현을 쓴다**

```python
# scripts/discovery/fundamental_risk_filter/p3_panel.py
"""P(3) 패널 결합 + 진단 — Phase 2B 가 검정 가능한지 여기서 판정한다.

읽기 전용. DB 접근 0 · DART 호출 0.

🔑 이 파일의 «진짜» 산출물은 parquet 이 아니라 리포트다. 배제 필터를 검정하려면
   배제될 관측이 충분히 있어야 하고, 그게 없으면 Phase 2B 는 설계할 값어치가 없다.

usage:
  PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/p3_panel.py
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dart_client import OUT_DIR  # noqa: E402
from p1_target import TARGET_PARQUET  # noqa: E402
from p2_features import FEATURES_PARQUET  # noqa: E402

PANEL_PARQUET = os.path.join(OUT_DIR, "frf_panel.parquet")
REPORT_TXT = os.path.join(OUT_DIR, "frf_panel_report.txt")


def usable(df):
    """창이 완결됐고 재무가 붙은 관측만. 원본을 건드리지 않는다."""
    return df[df["window_full"].fillna(False) & df["bsns_year"].notna()].copy()


def monthly_rates(df):
    if len(df) == 0:
        return pd.DataFrame(columns=["ym", "n", "crash_rate"])
    g = df.assign(ym=df["date"].str[:7]).groupby("ym")["crash"]
    return g.agg(n="size", crash_rate="mean").reset_index()


def main():
    tgt = pd.read_parquet(TARGET_PARQUET)
    feat = pd.read_parquet(FEATURES_PARQUET)
    panel = tgt.merge(feat.drop(columns=["from_date"], errors="ignore"),
                      on=["stock_code", "date"], how="left")
    panel.to_parquet(PANEL_PARQUET, index=False)

    u = usable(panel)
    lines = []
    lines.append(f"패널 {len(panel):,}행 · 종목 {panel['stock_code'].nunique():,}")
    lines.append(f"사용 가능(창 완결 ∧ 재무 매칭) {len(u):,}행 "
                 f"({100*len(u)/max(len(panel),1):.2f}%) · 종목 {u['stock_code'].nunique():,}")
    lines.append("")
    lines.append(f"기저 폭락률 {100*u['crash'].mean():.2f}%")
    lines.append("")
    lines.append("연속 축의 «분포» — 문턱을 제시하지 않는다")
    lines.append("  🔑 후보 문턱을 여기 찍으면 리포트를 읽은 사람이 그 값에 끌린다.")
    lines.append("     분위수만 보여주고 문턱 선택은 Phase 2B 의 PREREG 로 넘긴다.")
    for col in ("debt_ratio", "interest_coverage"):
        s = u[col].dropna()
        if len(s) == 0:
            lines.append(f"  {col:<18s} 값 없음")
            continue
        q = s.quantile([0.01, 0.05, 0.50, 0.95, 0.99])
        lines.append(f"  {col:<18s} n={len(s):>9,}  "
                     f"p01={q.loc[0.01]:9.3f} p05={q.loc[0.05]:9.3f} "
                     f"p50={q.loc[0.50]:9.3f} p95={q.loc[0.95]:9.3f} "
                     f"p99={q.loc[0.99]:9.3f}")
    ol = u["op_loss_years"].fillna(0)
    lines.append(f"  op_loss_years      분포 { {int(k): int(v) for k, v in ol.value_counts().sort_index().items()} }")
    lines.append("")
    lines.append("국면 진폭 (월별 폭락률, 창 완결분):")
    mr = monthly_rates(u)
    lines.append(f"  최소 {100*mr['crash_rate'].min():.2f}% · "
                 f"최대 {100*mr['crash_rate'].max():.2f}% · 월 {len(mr)}개")
    lines.append("")
    lines.append("🔑 Phase 2B 진행 판정 — 블록이 몇 개 생기는가:")
    lines.append("   관측 수가 아니라 «종목 수»를 본다. 블록 SE 의 블록이 종목이고,")
    lines.append("   관측 3만 개가 종목 20개에서 나왔다면 사실상 n=20 이다.")
    lines.append("   ⚠️ 아래 꼬리 마스크는 «분위수» 기반이라 후보 문턱을 제시하지 않는다.")
    masks = [("자본잠식(모수없음)", u["equity_impaired"].fillna(False))]
    for col, tail in (("debt_ratio", "hi"), ("interest_coverage", "lo")):
        s = u[col]
        for p in (0.01, 0.05):
            if s.notna().sum() == 0:
                continue
            cut = s.quantile(1 - p if tail == "hi" else p)
            m = s.gt(cut) if tail == "hi" else s.lt(cut)
            masks.append((f"{col} {tail} {int(p*100)}%", m.fillna(False)))
    for p in (0.01, 0.05):
        cut = ol.quantile(1 - p)
        masks.append((f"op_loss_years hi {int(p*100)}%", ol.gt(cut)))
    for name, mask in masks:
        sub = u[mask]
        rate = 100 * sub["crash"].mean() if len(sub) else float("nan")
        lines.append(f"   {name:<26s} 관측 {len(sub):>9,} · 종목 "
                     f"{sub['stock_code'].nunique():>5,} · 폭락률 {rate:6.2f}%")
    lines.append("")
    lines.append("   기저 대비 폭락률이 «올라가 있는» 축이 후보다. 다만 이 표는 문턱을")
    lines.append("   고르는 데 쓰지 않는다 — 그러면 사후 선택이다. 축의 «검정 가능성»만 본다.")

    text = "\n".join(lines)
    with open(REPORT_TXT, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)
    print(f"\n→ {PANEL_PARQUET}\n→ {REPORT_TXT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest tests/discovery/fundamental_risk_filter/test_panel.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 전체 스위트 + 실행**

```bash
python -m pytest tests/discovery/fundamental_risk_filter/ -v
PYTHONUTF8=1 python scripts/discovery/fundamental_risk_filter/p3_panel.py
```
Expected: **100 passed** (Phase 1 의 78 + T1 8 + T2 10 + T3 4)

리포트 전문을 보고할 것. ⚠️ **문턱을 고르라는 뜻이 아니다** — 리포트는 분위수와
분위수 기반 꼬리 마스크만 싣고 후보 문턱을 제시하지 않는다. 실제 격자는 Phase 2B 의
사전등록에서 동결한다. 판단할 것은 오직 **「이 축이 검정 가능한 블록 수를 갖는가」**다.

- [ ] **Step 6: 커밋**

```bash
git add scripts/discovery/fundamental_risk_filter/p3_panel.py tests/discovery/fundamental_risk_filter/test_panel.py
git commit -m "docs(frf): 패널 결합 + Phase 2B 진행 판정 리포트"
```

---

## Phase 2A 완료 조건

1. `tests/discovery/fundamental_risk_filter/` **100 passed**
2. 연도별 폭락률이 회귀 앵커(6.97 / 13.11 / 7.08 / 12.25 / 5.92)와 **±0.15%p** 일치
3. `000040` 경계가 `2022-05-18` / `2022-05-19` 에서 정확히 갈림
4. `frf_panel_report.txt` 에 축별 **관측 수·종목 수·폭락률**이 기록됨
5. 🔴 **라이브 코드 변경 0 · DB 쓰기 0 · DART 호출 0**

## 다음 (Phase 2B — 별도 계획)

`PREREG.md` 격자 동결 → 게이트 G0~G6 실행. **Phase 2B 계획은 `frf_panel_report.txt` 를 보고 쓴다.**

🔴 **먼저 답해야 할 질문**: 각 축의 배제 종목이 **블록 SE 가 성립할 만큼** 있는가.
Phase 1 에서 자본잠식 사업연도가 **50건**뿐이었다 — 일 단위로 펴도 종목 수는 그대로 50 미만일 수 있고,
그러면 그 축은 **검정력이 없어서** 격자에서 빠져야 한다. 이것은 실패가 아니라 **설계 입력**이다.

🟢 **리포트가 후보 문턱을 싣지 않도록 설계했다** — 분위수와 분위수 기반 꼬리 마스크만
보여준다. 그래서 리포트를 읽은 뒤에 PREREG 를 써도 「문턱을 분포에 맞춰 골랐다」가 되지 않는다.
⚠️ 단 **분위수 자체를 문턱으로 승격하지 말 것**(예: "p99 를 쓰자"). 그것도 같은 사후 선택이다.
문턱은 **도메인 근거**(회계·상장규정에서 통용되는 값)로 정하고 그 근거를 PREREG 에 적는다.
