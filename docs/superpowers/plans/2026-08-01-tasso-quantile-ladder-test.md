# 태쏘 「상승폭 조건부 하락폭 분위수 사다리」 4차 검정 — 실행계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 태쏘의 분할매수 진입 규칙(최고점 대비 하락폭 분위수 사다리)이 무작위 진입 대비 거래당 초과수익을 내는지를 사전등록된 판정규칙으로 검정한다.

**Architecture:** scratchpad 랩에 순수 함수 모듈 7개를 TDD로 쌓고, 사전등록 문서를 **먼저** 고정한 뒤 본실행 1회를 돌린다. 진입 위치만 격리하기 위해 청산·비중은 전략과 대조군에 동일 부착한다. 판정은 White Reality Check max-t.

**Tech Stack:** Python 3, pandas, numpy, scipy, psycopg2, pytest. 데이터는 PostgreSQL 16 `kis_template`.

## Global Constraints

- **랩 루트(LAB)**: `C:\Users\sttgp\AppData\Local\Temp\claude\D--GIT-kis-trading-template\89a952b4-838e-4700-b959-d2a9276819f2\scratchpad\tasso4`
- ⚠️ **라이브 트리(`D:\GIT\kis-trading-template`)에서 pytest·스모크를 절대 실행하지 않는다.** 모든 테스트는 LAB 안에서 돈다. 라이브 트리에는 문서(`docs/`)만 쓴다.
- ⚠️ **DB명 하드코딩 금지.** `resolve_daily_source_db()`(`RoboTrader_template/config/constants.py:216`) 경유. 기본값 `kis_template`.
- ⚠️ **`adj_factor` 를 곱하지 않는다.** close 는 이미 분할조정 연속시세다.
- ⚠️ **OHLC 전체에 0/NaN 가드.** `open=high=low=0` 18,147행이 존재하며 close 만 검사하면 살아남아 0 나누기로 결과를 파괴한다.
- **DB 접속**: host `127.0.0.1`, port **5433**, user `robotrader`, password `1234`.
- **`daily_prices.date` 는 text 타입** (`YYYY-MM-DD`). PK = `(stock_code, date)`.
- **왕복비용 0.21%** (거래세 0.18% + 수수료 0.015% 양방향) 를 모든 수익률에 반영.
- **사전등록(Task 1)을 커밋하기 전에는 어떤 백테스트 수치도 산출하지 않는다.** 이 순서가 이 검정의 유일한 방어선이다.
- **실행 환경(실측 확인됨)**: Python **3.9.13** (`C:\Program Files (x86)\Microsoft Visual Studio\Shared\Python39_64\python.exe`), pandas 2.2.3 · numpy 2.0.2 · scipy 1.13.1 · psycopg2 2.9.11 · pyarrow 21.0.0 · pytest 8.4.2. 프로젝트 venv 는 없다.
- ⚠️ **Python 3.9 이므로 모든 모듈 첫 줄(독스트링 다음)에 `from __future__ import annotations` 를 넣는다.** 없으면 `float | None` 같은 표기가 런타임에 죽는다. import 는 파일 상단에 모은다(`ruff check` E402).
- 설계 원문: `docs/superpowers/specs/2026-08-01-tasso-quantile-ladder-design.md`
- 캡처 원본: `D:\tmp\tasso\224364189017\slice_01~27.png`, `D:\tmp\tasso\224361924061\slice_01~19.png`

---

## File Structure

| 파일 | 책임 |
|---|---|
| `LAB/lab/data.py` | DB 로딩과 OHLC 가드. 다른 모듈은 DB를 직접 안 본다. |
| `LAB/lab/segments.py` | 상승구간(시작점·최고점) 탐지 3변형 |
| `LAB/lab/bands.py` | 하락폭 분포(PIT 추정 / 외생 상수) → 5레벨 사다리 |
| `LAB/lab/sim.py` | 체결·청산 시뮬, 절단 집계 |
| `LAB/lab/control.py` | 대조군 진입가 생성 |
| `LAB/lab/stats.py` | Δ·t·White Reality Check max-t·MDE |
| `LAB/lab/run.py` | 본실행 오케스트레이션, 산출물 5종 |
| `LAB/labels/labels.json` | 캡처 판독 라벨(1급 2건 + 2급 23종목) |
| `LAB/tests/test_*.py` | 모듈별 테스트 |

---

## Task 1: 사전등록 문서 고정

**Files:**
- Create: `C:\Users\sttgp\.claude\projects\D--GIT-kis-trading-template\memory\prereg-2026-08-01-tasso-quantile-ladder-sweep.md`

**Interfaces:**
- Consumes: 설계 문서 `docs/superpowers/specs/2026-08-01-tasso-quantile-ladder-design.md`
- Produces: 이후 모든 태스크가 참조하는 고정 파라미터 — 격자 정의, 판정규칙, MDE 목표

- [ ] **Step 1: 사전등록 문서를 아래 골격으로 작성**

frontmatter 는 기존 prereg 파일들과 동일 형식(`name`, `description`, `metadata.type: project`)을 쓴다. 본문에 다음을 **실행 전에** 못 박는다.

```markdown
## 1. 격자 (실행 전 고정)
- 상승구간 정의 변형: (a) 최저가 (b) 급등봉 시가 (c) 급등봉 직전봉 종가
- lookback W: {60, 120, 250} 거래일
- 활성화 상승폭 R: {30, 50, 100} %
- 유효기간 D: {20, 40} 거래일
- 밴드 폭 계수 c: {0.6, 0.8, 1.0}
- 분포 판본: {PIT 자체추정, 외생 상수 2점보간}
→ 캘리브레이션(Task 4) 통과 정의 1~3개만 본검정 진출. 총 셀 수는 Task 4 종료 시 확정하고 여기에 추가 기록한다.

## 2. 고정 파라미터 (스윕하지 않음)
- 분할 비중: 10 / 13 / 17 / 25 / 35 %
- 레벨 개수: 5, 등간격
- 청산: 마지막 분할 체결일 기준 20거래일 후 종가 (전략·대조군 동일)
- PIT 버킷: 상승폭 20~50 / 50~100 / 100~200 / 200~400 / 400%+
- PIT 최소표본: 버킷당 30건 (미만이면 진입 금지)
- PIT 극단값 제외: 상하 각 2.5%
- 비용: 왕복 0.21%

## 3. 판정규칙
- 1차 통계량: 거래당 초과수익 Δ = mean(전략) - mean(대조군)
- 판정: White Reality Check max-t, B = 1,000 부트스트랩, p < 0.05 이면 PASS
- 이 규칙 외의 어떤 사후 기준으로도 PASS 를 선언하지 않는다.

## 4. MDE (실행 전 산출, Task 7에서 채움)
- 예상 표본수 N, 거래당 수익률 표준편차 s 로부터 α=0.05·power=0.8 기준 MDE 를 적는다.
- 3차 결론이 "거래당 1.7%p 이상의 엣지 없음" 이었으므로 이번 MDE 를 그와 나란히 적는다.

## 5. 필수 산출물 (FAIL 이어도 전부 낸다)
1. 연도별 분해 (2026 포함/제외)
2. 전략·대조군 **양쪽** 절단 건수
3. 셀별 표본수
4. 상승폭 버킷별 분해
5. 캘리브레이션 채점표

## 6. 예상과 그 근거
- 예상 FAIL. 근거 3가지(계열 3연속 FAIL / 평균회귀라 발굴 종결 결론과 같은 공간 / 그의 실적은 합성 불장 1개월 표본).
- FAIL 은 "엣지 없음" 이 아니라 "MDE 이상의 엣지 없음" 으로만 서술한다.

## 7. 알려진 한계
- 생존편향: daily_prices 는 2026-06-22 일괄 백필이라 상폐 종목 부재. 이 전략은 "급등 후 크게 빠진 종목 매수" 라 편향을 **낙관 방향**으로 받는다. 결론에 방향성을 명시한다.
- 2026 합성 불장(~3배).
- `중심=(Q1+Q3)/2`, `폭=0.8×IQR` 는 **삼성 1건에서만 검증된 규칙**이다(다날은 Q1/Q3 미관측).
```

- [ ] **Step 2: MEMORY.md 인덱스에 한 줄 추가**

`## 최근 메모` 최상단에 추가:
```markdown
- [🔬 2026-08-01 **태쏘 4차 사전등록 — 상승폭 조건부 하락폭 분위수 사다리(진입 코어 격리)**](prereg-2026-08-01-tasso-quantile-ladder-sweep.md) — 실행 전 격자·판정규칙 고정. 설계 `docs/superpowers/specs/2026-08-01-tasso-quantile-ladder-design.md`.
```

- [ ] **Step 3: 사장님께 커밋 승인 요청 후 커밋**

git 편집은 사용자 확인 사항이다. 승인 후:
```bash
git add docs/superpowers/specs/2026-08-01-tasso-quantile-ladder-design.md docs/superpowers/plans/2026-08-01-tasso-quantile-ladder-test.md
git commit -m "docs(spec): 태쏘 4차 검정 설계·실행계획 — 진입 코어 격리, 사전등록 선행"
```

---

## Task 2: 데이터 로더와 OHLC 가드

**Files:**
- Create: `LAB/lab/data.py`, `LAB/lab/__init__.py`
- Test: `LAB/tests/test_data.py`

**Interfaces:**
- Produces:
  - `load_daily(start: str, end: str) -> pd.DataFrame` — 컬럼 `stock_code, date, open, high, low, close, volume, trading_value, market_cap`
  - `drop_bad_ohlc(df: pd.DataFrame) -> pd.DataFrame`

- [ ] **Step 1: 실패 테스트 작성**

`LAB/tests/test_data.py`:
```python
import pandas as pd
from lab.data import drop_bad_ohlc, load_daily
from lab.data import resolve_daily_source_db


def test_resolver_points_at_kis_template():
    assert resolve_daily_source_db() == "kis_template"


def test_drop_bad_ohlc_removes_zero_open_even_when_close_is_valid():
    """close 만 검사하면 살아남는 행을 잡는지 — 18,147행 클래스."""
    df = pd.DataFrame({
        "stock_code": ["A", "B"],
        "date": ["2026-01-02", "2026-01-02"],
        "open": [0.0, 100.0],
        "high": [0.0, 110.0],
        "low": [0.0, 95.0],
        "close": [1000.0, 105.0],
        "volume": [0, 10],
        "trading_value": [0, 1000],
        "market_cap": [1e9, 1e9],
    })
    out = drop_bad_ohlc(df)
    assert list(out["stock_code"]) == ["B"]


def test_loader_never_reads_adj_factor():
    import inspect
    assert "adj_factor" not in inspect.getsource(load_daily)
```

- [ ] **Step 2: 실패 확인**

Run: `cd LAB && python -m pytest tests/test_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lab'`

- [ ] **Step 3: 구현**

`LAB/lab/__init__.py` 는 빈 파일. `LAB/lab/data.py`:
```python
"""태쏘 4차 검정 랩 — 데이터 로딩과 가드.

⚠️ 라이브 트리에서 실행 금지. 이 파일은 scratchpad 랩에만 둔다.
"""
from __future__ import annotations

import sys

import pandas as pd
import psycopg2

REPO = r"D:\GIT\kis-trading-template\RoboTrader_template"
if REPO not in sys.path:
    sys.path.insert(0, REPO)
from config.constants import resolve_daily_source_db  # noqa: E402

PG = dict(host="127.0.0.1", port=5433, user="robotrader", password="1234")
OHLC = ("open", "high", "low", "close")


def _conn():
    return psycopg2.connect(dbname=resolve_daily_source_db(), **PG)


def drop_bad_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """OHLC 중 하나라도 0 이하이거나 NaN 이면 행을 버린다.

    close 만 검사하면 open=high=low=0 인 18,147행이 살아남아
    체결 시뮬에서 0 나누기로 결과를 파괴한다.
    """
    bad = df[list(OHLC)].isna().any(axis=1)
    for col in OHLC:
        bad = bad | (df[col] <= 0)
    return df.loc[~bad].reset_index(drop=True)


def load_daily(start: str, end: str) -> pd.DataFrame:
    """일봉 로딩. adj_factor 는 읽지 않는다(곱하면 분할일 가짜 절벽)."""
    sql = """
        select stock_code, date, open, high, low, close,
               volume, trading_value, market_cap
        from daily_prices
        where date >= %s and date <= %s
        order by stock_code, date
    """
    with _conn() as conn:
        df = pd.read_sql(sql, conn, params=(start, end))
    return drop_bad_ohlc(df)
```

- [ ] **Step 4: 통과 확인**

Run: `cd LAB && python -m pytest tests/test_data.py -v`
Expected: 3 passed

- [ ] **Step 5: 실데이터 스모크 (건수 대조)**

Run: `cd LAB && python -c "from lab.data import load_daily; d=load_daily('2021-01-04','2026-07-31'); print(len(d), d['stock_code'].nunique())"`
Expected: 가드 적용 후 행수가 2,850,450 보다 **작아야** 한다(18,147행 클래스가 빠지므로). 종목수는 2,606 근방. 행수가 정확히 2,850,450 이면 가드가 안 걸린 것이므로 멈추고 원인을 찾는다.

---

## Task 3: 캡처 라벨 판독

**Files:**
- Create: `LAB/labels/labels.json`
- Test: `LAB/tests/test_labels.py`

**Interfaces:**
- Produces: `labels.json` — `{"grade1": [...], "grade2": [...]}`

- [ ] **Step 1: 1급 라벨 2건을 먼저 기록**

```json
{
  "grade1": [
    {"name": "삼성전자", "code": "005930", "timeframe": "month",
     "start": 53200, "peak": 380000, "gain_pct": 614.3,
     "q1": 0.353, "median": 0.427, "q3": 0.560,
     "sample_n": 119, "range": [0.203, 0.680], "outliers_dropped": 6,
     "levels": [238165, 222395, 206625, 190855, 175085],
     "weights": [10, 13, 17, 25, 35],
     "source": "D:/tmp/tasso/224361924061/slice_05.png"},
    {"name": "다날", "code": null, "timeframe": "min60",
     "start": 3930, "peak": 5100, "gain_pct": 29.8,
     "q1": null, "median": null, "q3": null,
     "levels": [4452, 4371, 4289, 4208, 4126],
     "weights": [10, 13, 17, 25, 35],
     "source": "D:/tmp/tasso/224361924061/slice_11.png"}
  ],
  "grade2": []
}
```

- [ ] **Step 2: 27장을 순서대로 판독해 `grade2` 를 채운다**

`D:\tmp\tasso\224364189017\slice_01.png` 부터 `slice_27.png` 까지 Read 로 연다. 각 종목마다 다음을 뽑는다.

- `name`, 일봉 차트의 `최고 X (MM/DD)` · `최저 X (MM/DD)` 라벨
- 체결표의 `일자 / 매입가 / 매도체결가 / 수익률` 전 행

기록 형식(가온칩스 예시 — slice_02 에서 실제 판독한 값):
```json
{"name": "가온칩스", "high": 83200, "high_date": "04/27",
 "low": 34950, "low_date": "07/03",
 "fills": [
   {"date": "2026-07-09", "buy": 42260, "sell": 53000, "pct": 25.10},
   {"date": "2026-07-14", "buy": 47040, "sell": 54500, "pct": 15.60},
   {"date": "2026-07-14", "buy": 47040, "sell": 53900, "pct": 14.32},
   {"date": "2026-07-14", "buy": 50000, "sell": 54500, "pct": 8.74},
   {"date": "2026-07-14", "buy": 50000, "sell": 52500, "pct": 4.75}
 ],
 "source": "D:/tmp/tasso/224364189017/slice_02.png"}
```

⚠️ 판독 불가(라벨 잘림·화질)한 항목은 **추측해서 채우지 말고** `null` 로 두고 `"note"` 에 사유를 적는다. 채점에서 제외된다.

- [ ] **Step 3: 종목명 → 종목코드 매핑**

`daily_prices` 에는 종목명 컬럼이 없다. 아래 15건은 DB(`screener_snapshots` ∪ `candidate_stocks` ∪ `virtual_trading_records`)에서 **실측 확인된 매핑**이므로 그대로 쓴다.

| 종목명 | 코드 | 종목명 | 코드 | 종목명 | 코드 |
|---|---|---|---|---|---|
| 가온칩스 | 399720 | 금호전기 | 001210 | 다날 | 064260 |
| 다스코 | 058730 | 데이타솔루션 | 263800 | 마키나락스 | 477850 |
| 모나미 | 005360 | 삼기 | 122350 | 씨피시스템 | 413630 |
| 지엔씨에너지 | 119850 | 코스모로보틱스 | 439960 | 티엑스알로보틱스 | 484810 |
| 한성기업 | 003680 | 한성크린텍 | 066980 | 현대약품 | 004310 |

나머지 7건(**금호건설·남화토건·동신건설·삼호개발·삼화전자·셀바스AI·에스폴리텍**)은 우리 봇이 스크리닝한 적이 없어 DB에 없다. `finance.naver.com` 종목 검색으로 코드를 확인해 채운다.

⚠️ **코드를 추측해서 넣지 말 것.** 확인 못 한 종목은 `"code": null` 로 두고 `"note": "코드 미확인"` 을 적는다. 채점에서 제외되며, 제외 건수를 `calibration_scores.csv` 옆에 기록한다. 잘못된 코드는 엉뚱한 종목의 가격으로 채점해 정의 선정을 통째로 오염시킨다.

- [ ] **Step 4: 라벨 정합성 테스트 작성**

`LAB/tests/test_labels.py`:
```python
import json
from pathlib import Path

LABELS = json.loads((Path(__file__).parent.parent / "labels" / "labels.json").read_text(encoding="utf-8"))


def test_grade1_samsung_levels_are_evenly_spaced():
    s = [g for g in LABELS["grade1"] if g["name"] == "삼성전자"][0]
    lv = s["levels"]
    gaps = [lv[i] - lv[i + 1] for i in range(4)]
    assert max(gaps) - min(gaps) < 5, gaps


def test_grade1_danal_start_is_not_the_low():
    d = [g for g in LABELS["grade1"] if g["name"] == "다날"][0]
    assert d["start"] == 3930          # 최저 3805 와 다름 — (a)변형 반증 근거


def test_reported_returns_are_net_of_cost():
    """그의 표기 수익률은 gross 보다 0.2~0.35%p 낮다 = 비용 차감 후."""
    gaps = []
    for stock in LABELS["grade2"]:
        for f in stock.get("fills", []):
            if not f.get("buy") or not f.get("sell") or f.get("pct") is None:
                continue
            gross = (f["sell"] - f["buy"]) / f["buy"] * 100
            gaps.append(gross - f["pct"])
    assert len(gaps) >= 20, f"판독된 체결이 너무 적다: {len(gaps)}"
    assert 0.15 < sum(gaps) / len(gaps) < 0.40, sum(gaps) / len(gaps)
```

- [ ] **Step 5: 통과 확인**

Run: `cd LAB && python -m pytest tests/test_labels.py -v`
Expected: 3 passed. `test_reported_returns_are_net_of_cost` 가 실패하면 판독 오류이므로 해당 종목을 다시 연다.

- [ ] **Step 6: 커밋**

```bash
cd "$LAB"
[ -d .git ] || git init -q
git add . && git commit -q -m "labels: 태쏘 캡처 판독 라벨 1급 2건 + 2급 N종목"
```
LAB 은 독립 저장소다. 라이브 트리 저장소에 커밋하지 않는다.

---

## Task 4: 상승구간 탐지 3변형

**Files:**
- Create: `LAB/lab/segments.py`
- Test: `LAB/tests/test_segments.py`

**Interfaces:**
- Consumes: `lab.data.load_daily`
- Produces:
  - `Segment` dataclass — `code: str, start_date: str, start_px: float, peak_date: str, peak_px: float, gain: float`
  - `find_segments(df: pd.DataFrame, variant: str, lookback: int, min_gain: float) -> list[Segment]`
    - `variant` ∈ `{"low", "surge_open", "prev_close"}`

- [ ] **Step 1: 실패 테스트 작성**

`LAB/tests/test_segments.py`:
```python
import pandas as pd
from lab.segments import find_segments


def _frame(rows):
    return pd.DataFrame(rows, columns=["stock_code", "date", "open", "high", "low", "close", "volume"])


_RALLY = [
    ["A", "2026-01-02", 100, 105, 95, 100, 1000],
    ["A", "2026-01-05", 100, 104, 90, 96, 1000],   # 최저 90
    ["A", "2026-01-06", 96, 150, 96, 148, 9000],   # 급등봉 (시가 96, 직전봉 종가 96)
    ["A", "2026-01-07", 148, 200, 145, 195, 5000], # 최고 200 — 오늘이 창 최고
]


def test_low_variant_uses_the_lowest_low_as_start():
    segs = find_segments(_frame(_RALLY), variant="low", lookback=3, min_gain=0.30)
    assert len(segs) == 1
    assert segs[0].start_px == 90
    assert segs[0].peak_px == 200


def test_surge_open_variant_starts_at_the_surge_bar_open():
    segs = find_segments(_frame(_RALLY), variant="surge_open", lookback=3, min_gain=0.30)
    assert segs[0].start_px == 96


def test_prev_close_variant_starts_at_the_bar_before_the_surge():
    segs = find_segments(_frame(_RALLY), variant="prev_close", lookback=3, min_gain=0.30)
    assert segs[0].start_px == 96


def test_segment_is_dropped_when_gain_below_activation():
    df = _frame([
        ["A", "2026-01-02", 100, 105, 95, 100, 1000],
        ["A", "2026-01-05", 100, 110, 99, 108, 3000],
        ["A", "2026-01-06", 108, 112, 107, 110, 3000],
    ])
    assert find_segments(df, variant="low", lookback=2, min_gain=0.30) == []


def test_no_segment_emitted_on_a_day_that_is_not_a_window_high():
    """구간은 '새 고점을 찍은 날'에만 발생한다 — 하락 중에는 안 생긴다."""
    rows = _RALLY + [["A", "2026-01-08", 195, 196, 180, 182, 4000]]
    segs = find_segments(_frame(rows), variant="low", lookback=3, min_gain=0.30)
    assert all(s.peak_date != "2026-01-08" for s in segs)


def test_many_segments_across_a_long_history():
    """종목당 1건만 나오면 5.6년 백테스트 표본이 붕괴한다."""
    rows = []
    for cycle in range(5):
        base = 100 + cycle
        rows += [
            ["A", f"2026-{cycle+1:02d}-02", base, base + 5, base - 5, base, 1000],
            ["A", f"2026-{cycle+1:02d}-05", base, base + 4, base - 10, base - 4, 1000],
            ["A", f"2026-{cycle+1:02d}-06", base - 4, base + 50, base - 4, base + 48, 9000],
            ["A", f"2026-{cycle+1:02d}-07", base + 48, base + 100, base + 45, base + 95, 5000],
        ]
    segs = find_segments(_frame(rows), variant="low", lookback=3, min_gain=0.30)
    assert len(segs) >= 4, len(segs)
```

- [ ] **Step 2: 실패 확인**

Run: `cd LAB && python -m pytest tests/test_segments.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lab.segments'`

- [ ] **Step 3: 구현**

`LAB/lab/segments.py`:
```python
"""상승구간(시작점 → 최고점) 탐지 3변형."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

VARIANTS = ("low", "surge_open", "prev_close")
SURGE_VOL_MULT = 3.0   # 급등봉 = 거래량이 lookback 중앙값의 3배 이상


@dataclass(frozen=True)
class Segment:
    code: str
    start_date: str
    start_px: float
    peak_date: str
    peak_px: float
    gain: float


def _surge_idx(g: pd.DataFrame, low_pos: int) -> int | None:
    """최저가 이후 첫 급등봉 위치. 없으면 None."""
    med = g["volume"].iloc[: low_pos + 1].median()
    if not med or med <= 0:
        med = g["volume"].median()
    for i in range(low_pos + 1, len(g)):
        if g["volume"].iat[i] >= SURGE_VOL_MULT * med:
            return i
    return None


def _start_price(w: pd.DataFrame, low_pos: int, variant: str) -> float | None:
    if variant == "low":
        return float(w["low"].iat[low_pos])
    s = _surge_idx(w, low_pos)
    if s is None or s == 0:
        return None
    return float(w["open"].iat[s]) if variant == "surge_open" else float(w["close"].iat[s - 1])


def find_segments(df: pd.DataFrame, variant: str, lookback: int, min_gain: float) -> list[Segment]:
    """시간축을 훑으며 '새 고점을 찍은 날'마다 상승구간을 발생시킨다.

    ⚠️ 종목당 마지막 창 하나만 보면 5.6년 백테스트 표본이 종목당 1건으로
       붕괴해 MDE 게이트를 통과할 수 없다. 반드시 전 기간을 스캔한다.
    같은 (종목, 시작일) 조합은 최고 peak 하나로 접는다.
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant: {variant}")
    out: list[Segment] = []
    for code, g in df.groupby("stock_code", sort=False):
        g = g.reset_index(drop=True)
        best: dict[tuple[str, str], Segment] = {}
        for t in range(lookback, len(g)):
            w = g.iloc[t - lookback : t + 1].reset_index(drop=True)
            if float(w["high"].iat[-1]) < float(w["high"].max()):
                continue                      # 오늘이 창 최고가가 아니면 발생시키지 않는다
            low_pos = int(w["low"].iloc[:-1].idxmin())
            start_px = _start_price(w, low_pos, variant)
            if start_px is None or start_px <= 0:
                continue
            peak_px = float(w["high"].iat[-1])
            gain = peak_px / start_px - 1.0
            if gain < min_gain:
                continue
            seg = Segment(
                code=str(code),
                start_date=str(w["date"].iat[low_pos]),
                start_px=start_px,
                peak_date=str(w["date"].iat[-1]),
                peak_px=peak_px,
                gain=gain,
            )
            key = (seg.code, seg.start_date)
            if key not in best or seg.peak_px > best[key].peak_px:
                best[key] = seg
        out.extend(best.values())
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `cd LAB && python -m pytest tests/test_segments.py -v`
Expected: **6 passed**. (구현·테스트 모두 실측 확인됨: low→90, surge_open→96, prev_close→96, 미달구간→[], 하락일 미발생, 다구간 5건 검출.)

- [ ] **Step 5: 커밋**

```bash
cd LAB && git add lab/segments.py tests/test_segments.py && git commit -q -m "feat(segments): 상승구간 탐지 3변형"
```

---

## Task 5: 밴드·사다리 생성 (부호 회귀 가드 포함)

**Files:**
- Create: `LAB/lab/bands.py`
- Test: `LAB/tests/test_bands.py`

**Interfaces:**
- Consumes: `lab.segments.Segment`
- Produces:
  - `WEIGHTS: tuple[float, ...]` = `(0.10, 0.13, 0.17, 0.25, 0.35)`
  - `ladder(peak: float, q1: float, q3: float, c: float = 0.8) -> list[float]`
  - `pit_quantiles(history: list[tuple[float, float]], gain: float, min_n: int = 30) -> tuple[float, float] | None`
  - `exogenous_quantiles(gain: float) -> tuple[float, float]`

- [ ] **Step 1: 실패 테스트 작성 — 삼성 화면 5값을 못 박는다**

`LAB/tests/test_bands.py`:
```python
import pytest
from lab.bands import WEIGHTS, exogenous_quantiles, ladder, pit_quantiles


def test_ladder_reproduces_the_samsung_screen():
    """화면 실측 5레벨. 부호가 뒤집히면 여기서 죽는다."""
    got = ladder(peak=380_000, q1=0.353, q3=0.560, c=0.8)
    expected = [238_165, 222_395, 206_625, 190_855, 175_085]
    for g, e in zip(got, expected):
        assert abs(g - e) < 300, (got, expected)


def test_first_level_is_the_highest_price_and_last_gets_the_most_weight():
    """사다리 방향 + 하방가중. 총 체결금액은 뒤집혀도 비슷해서 합계로는 안 잡힌다."""
    lv = ladder(peak=380_000, q1=0.353, q3=0.560, c=0.8)
    assert lv[0] > lv[-1]
    assert WEIGHTS[-1] > WEIGHTS[0]
    assert abs(sum(WEIGHTS) - 1.0) < 1e-9


def test_ladder_is_evenly_spaced():
    lv = ladder(peak=5_100, q1=0.119, q3=0.199, c=0.8)
    gaps = [lv[i] - lv[i + 1] for i in range(4)]
    assert max(gaps) - min(gaps) < 1e-6


def test_pit_returns_none_when_bucket_sample_is_too_small():
    history = [(0.4, 0.3)] * 5          # (gain, drawdown) 5건뿐
    assert pit_quantiles(history, gain=0.4, min_n=30) is None


def test_pit_uses_only_the_matching_gain_bucket():
    history = [(0.4, 0.10)] * 40 + [(5.0, 0.50)] * 40
    q1, q3 = pit_quantiles(history, gain=0.4, min_n=30)
    assert q1 == pytest.approx(0.10, abs=1e-6)
    assert q3 == pytest.approx(0.10, abs=1e-6)


def test_exogenous_interpolation_matches_the_two_observed_points():
    _, _ = exogenous_quantiles(0.298)
    c_danal = sum(exogenous_quantiles(0.298)) / 2
    c_samsung = sum(exogenous_quantiles(6.143)) / 2
    assert c_danal == pytest.approx(0.1590, abs=1e-3)
    assert c_samsung == pytest.approx(0.4565, abs=1e-3)
```

- [ ] **Step 2: 실패 확인**

Run: `cd LAB && python -m pytest tests/test_bands.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lab.bands'`

- [ ] **Step 3: 구현**

`LAB/lab/bands.py`:
```python
"""하락폭 분포 → 5분할 매수 사다리.

역설계 근거: 삼성 화면 Q1 35.3 / Q3 56.0 → 레벨 5개가
37.33 / 41.48 / 45.63 / 49.78 / 53.93 % 하락 지점에 4.15%p 등간격으로 놓임.
중심 = (Q1+Q3)/2 = 45.65, 전체폭 = 16.60 = 0.802 × IQR(20.7).
⚠️ 이 계수는 삼성 1건에서만 검증됐다(다날은 Q1/Q3 미관측).
"""
from __future__ import annotations

import math

import numpy as np

WEIGHTS: tuple[float, ...] = (0.10, 0.13, 0.17, 0.25, 0.35)

# 상승폭 버킷 하한 (설계 §7)
BUCKETS = (0.20, 0.50, 1.00, 2.00, 4.00)

# 외생 상수 2점: (상승폭, 밴드중심) — 삼성/다날 화면 실측
_EXO = ((0.298, 0.1590), (6.143, 0.4565))
_EXO_IQR_RATIO = 0.207 / 0.4565   # 삼성 IQR / 중심 → 중심에 비례해 IQR 추정


def ladder(peak: float, q1: float, q3: float, c: float = 0.8) -> list[float]:
    """5분할 매수 지정가. 1차가 최고가(하락폭 최소), 5차가 최저가."""
    center = (q1 + q3) / 2.0
    width = c * (q3 - q1)
    return [peak * (1.0 - (center + (k - 3) * width / 4.0)) for k in range(1, 6)]


def _bucket(gain: float) -> int:
    idx = 0
    for i, lo in enumerate(BUCKETS):
        if gain >= lo:
            idx = i
    return idx


def pit_quantiles(history, gain: float, min_n: int = 30, trim: float = 0.025):
    """과거 (상승폭, 하락폭) 표본에서 같은 버킷의 Q1/Q3. 표본 부족이면 None."""
    b = _bucket(gain)
    dd = np.array([d for g, d in history if _bucket(g) == b], dtype=float)
    if dd.size < min_n:
        return None
    lo, hi = np.quantile(dd, [trim, 1.0 - trim])
    dd = dd[(dd >= lo) & (dd <= hi)]
    if dd.size < min_n:
        return None
    q1, q3 = np.quantile(dd, [0.25, 0.75])
    return float(q1), float(q3)


def exogenous_quantiles(gain: float) -> tuple[float, float]:
    """삼성·다날 2점을 log(상승폭) 상에서 선형보간해 밴드를 고정한다.

    ⚠️ 2점 보간이라 상승폭 29.8% 미만과 614% 초과는 외삽이다.
    """
    (g0, c0), (g1, c1) = _EXO
    x0, x1, x = math.log(g0), math.log(g1), math.log(max(gain, 1e-6))
    t = (x - x0) / (x1 - x0)
    center = c0 + t * (c1 - c0)
    iqr = center * _EXO_IQR_RATIO
    return center - iqr / 2.0, center + iqr / 2.0
```

- [ ] **Step 4: 통과 확인**

Run: `cd LAB && python -m pytest tests/test_bands.py -v`
Expected: 6 passed

- [ ] **Step 5: 변이 주입으로 가드의 판별력 실측**

`ladder` 의 `(k - 3)` 을 `(3 - k)` 로 잠시 바꾸고 테스트를 돌린다.
Expected: `test_ladder_reproduces_the_samsung_screen` 과 `test_first_level_is_the_highest_price_and_last_gets_the_most_weight` 가 **둘 다 FAIL**. 하나만 실패하면 가드가 부족한 것이므로 보강한다. 확인 후 되돌린다.

- [ ] **Step 6: 커밋**

```bash
cd LAB && git add lab/bands.py tests/test_bands.py && git commit -q -m "feat(bands): 하락폭 분위수 사다리 + 삼성 화면 5값 회귀 가드"
```

---

## Task 6: 캘리브레이션 채점 → 정의 선정

**Files:**
- Create: `LAB/lab/calibrate.py`
- Test: `LAB/tests/test_calibrate.py`

**Interfaces:**
- Consumes: `labels.json`, `lab.segments.find_segments`, `lab.bands.ladder`
- Produces:
  - `score_grade1(seg: Segment, label: dict) -> float` — 시작점·최고점 상대오차 합
  - `best_subset_avg(levels: list[float], weights) -> list[float]` — 연속 부분집합 가중평균 전부
  - `score_grade2(levels: list[float], fills: list[dict]) -> float`

- [ ] **Step 1: 실패 테스트 작성**

`LAB/tests/test_calibrate.py`:
```python
import pytest
from lab.bands import WEIGHTS
from lab.calibrate import best_subset_avg, score_grade2


def test_subset_averages_include_the_danal_observed_prices():
    """다날 실제 매입가 4,404.36 = 1·2차 가중평균, 4,297.96 = 1~4차 가중평균."""
    levels = [4452.0, 4371.0, 4289.0, 4208.0, 4126.0]
    avgs = best_subset_avg(levels, WEIGHTS)
    assert any(abs(a - 4404.36) < 5 for a in avgs), avgs
    assert any(abs(a - 4297.96) < 5 for a in avgs), avgs


def test_score_uses_subset_average_not_single_level():
    """단일 레벨 최근접으로 채점하면 정답 규칙을 탈락시킨다."""
    levels = [4452.0, 4371.0, 4289.0, 4208.0, 4126.0]
    fills = [{"buy": 4404.36}]
    assert score_grade2(levels, fills) == pytest.approx(0.0, abs=2e-3)
```

- [ ] **Step 2: 실패 확인**

Run: `cd LAB && python -m pytest tests/test_calibrate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lab.calibrate'`

- [ ] **Step 3: 구현**

`LAB/lab/calibrate.py`:
```python
"""후보 정의를 캡처 라벨에 맞춰 채점한다."""
from __future__ import annotations


def best_subset_avg(levels, weights) -> list[float]:
    """1차부터 연속으로 n개 체결됐을 때의 가중평균 전부 (n = 1..5)."""
    out = []
    for n in range(1, len(levels) + 1):
        w = weights[:n]
        tot = sum(w)
        out.append(sum(l * wi for l, wi in zip(levels[:n], w)) / tot)
    return out


def score_grade2(levels, fills, weights=None) -> float:
    """실제 매입가와 '연속 부분집합 가중평균' 사이 최소 상대오차의 평균."""
    from lab.bands import WEIGHTS
    weights = weights or WEIGHTS
    cands = best_subset_avg(levels, weights) + list(levels)
    errs = []
    for f in fills:
        buy = f.get("buy")
        if not buy:
            continue
        errs.append(min(abs(c - buy) / buy for c in cands))
    return sum(errs) / len(errs) if errs else float("inf")


def score_grade1(seg, label) -> float:
    """시작점·최고점 상대오차의 합. 낮을수록 좋다."""
    return (abs(seg.start_px - label["start"]) / label["start"]
            + abs(seg.peak_px - label["peak"]) / label["peak"])
```

- [ ] **Step 4: 통과 확인**

Run: `cd LAB && python -m pytest tests/test_calibrate.py -v`
Expected: 2 passed

- [ ] **Step 5: 전 격자 채점 실행 → 상위 정의 1~3개 선정**

`LAB/lab/calibrate_run.py` 를 만든다:
```python
"""정의 격자를 라벨에 맞춰 채점하고 상위 3개를 고른다."""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import pandas as pd

from lab.bands import exogenous_quantiles, ladder
from lab.calibrate import score_grade1, score_grade2
from lab.data import load_daily
from lab.segments import find_segments

VARIANTS = ("low", "surge_open", "prev_close")
LOOKBACKS = (60, 120, 250)
MIN_GAINS = (0.30, 0.50, 1.00)
VALID_DAYS = 20


def main() -> None:
    out = Path("out")
    out.mkdir(exist_ok=True)
    labels = json.loads(Path("labels/labels.json").read_text(encoding="utf-8"))
    bars = load_daily("2021-01-04", "2026-07-31")

    codes = {s["code"] for s in labels["grade1"] + labels["grade2"] if s.get("code")}
    sub = bars[bars["stock_code"].isin(codes)]
    skipped = [s["name"] for s in labels["grade2"] if not s.get("code")]

    rows = []
    for variant, lb, mg in itertools.product(VARIANTS, LOOKBACKS, MIN_GAINS):
        segs = find_segments(sub, variant, lb, mg)
        by_code: dict[str, list] = {}
        for s in segs:
            by_code.setdefault(s.code, []).append(s)

        g1 = [min(score_grade1(s, lab) for s in by_code[lab["code"]])
              for lab in labels["grade1"]
              if lab.get("code") and lab["code"] in by_code]

        g2 = []
        for lab in labels["grade2"]:
            code, fills = lab.get("code"), lab.get("fills") or []
            if not code or code not in by_code or not fills:
                continue
            best = float("inf")
            for s in by_code[code]:
                q1, q3 = exogenous_quantiles(s.gain)
                best = min(best, score_grade2(ladder(s.peak_px, q1, q3, 0.8), fills))
            g2.append(best)

        rows.append({"variant": variant, "lookback": lb, "min_gain": mg,
                     "n_segments": len(segs),
                     "g1_n": len(g1), "g1_err": sum(g1) / len(g1) if g1 else None,
                     "g2_n": len(g2), "g2_err": sum(g2) / len(g2) if g2 else None})

    df = pd.DataFrame(rows)
    df.to_csv(out / "calibration_scores.csv", index=False)

    ranked = (df.dropna(subset=["g1_err", "g2_err"])
                .assign(score=lambda x: x["g1_err"].rank() + x["g2_err"].rank())
                .sort_values("score").head(3))
    selected = [{"name": f"{r.variant}-lb{r.lookback}-mg{r.min_gain}",
                 "variant": r.variant, "lookback": int(r.lookback),
                 "min_gain": float(r.min_gain), "valid_days": VALID_DAYS}
                for r in ranked.itertuples()]
    (out / "selected_definitions.json").write_text(
        json.dumps(selected, indent=2, ensure_ascii=False), encoding="utf-8")

    print(df.to_string(index=False))
    print("\n코드 미확인으로 채점 제외:", skipped or "없음")
    print("selected:", json.dumps(selected, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

Run: `cd LAB && python -m lab.calibrate_run`
Expected: `out/calibration_scores.csv` 27행(3×3×3), `out/selected_definitions.json` 3건, 그리고 채점 제외 종목 목록이 출력된다.

⚠️ `g1_n` 이 0이면 1급 라벨이 한 건도 안 걸린 것이다. 그 상태로 진행하면 정의 선정이 2급 라벨만으로 이뤄지므로, 멈추고 lookback·min_gain 범위를 사전등록에 기록한 뒤 넓힌다.

**상위 1~3개 정의만** 사전등록 문서 §1에 추가 기록한다.

⚠️ 여기서 정의를 고른 뒤에는 **다시 바꾸지 않는다.** 본검정 결과를 보고 정의를 갈아끼우면 검정이 무효다.

- [ ] **Step 6: 커밋**

```bash
cd LAB && git add lab/calibrate.py lab/calibrate_run.py tests/test_calibrate.py out/calibration_scores.csv && git commit -q -m "feat(calibrate): 라벨 채점 + 정의 선정"
```

---

## Task 7: 체결·청산 시뮬과 대조군

**Files:**
- Create: `LAB/lab/sim.py`, `LAB/lab/control.py`
- Test: `LAB/tests/test_sim.py`

**Interfaces:**
- Produces:
  - `Trade` dataclass — `code, entry_date, avg_cost, exit_date, exit_px, ret_net, filled_n, truncated: bool`
  - `simulate(bars: pd.DataFrame, levels: list[float], hold_days: int = 20, cost: float = 0.0021) -> Trade | None`
  - `control_levels(bars_on_entry_day: pd.Series, rng) -> list[float]`

- [ ] **Step 1: 실패 테스트 작성**

`LAB/tests/test_sim.py`:
```python
import numpy as np
import pandas as pd
from lab.sim import simulate


def _bars(rows):
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close"])


def test_fill_happens_at_the_level_when_low_touches_it():
    bars = _bars([["2026-01-02", 100, 101, 89, 95]] + [["2026-01-%02d" % d, 95, 96, 94, 95] for d in range(3, 25)])
    t = simulate(bars, levels=[90.0], hold_days=20)
    assert t.avg_cost == 90.0


def test_gap_down_fills_at_the_open_not_the_level():
    bars = _bars([["2026-01-02", 80, 82, 78, 81]] + [["2026-01-%02d" % d, 81, 82, 80, 81] for d in range(3, 25)])
    t = simulate(bars, levels=[90.0], hold_days=20)
    assert t.avg_cost == 80.0


def test_trade_is_marked_truncated_when_data_ends_before_hold_period():
    bars = _bars([["2026-01-02", 100, 101, 89, 95], ["2026-01-05", 95, 96, 94, 95]])
    t = simulate(bars, levels=[90.0], hold_days=20)
    assert t.truncated is True


def test_cost_is_deducted_from_the_return():
    bars = _bars([["2026-01-02", 100, 101, 89, 95]] + [["2026-01-%02d" % d, 100, 100, 100, 100] for d in range(3, 25)])
    t = simulate(bars, levels=[90.0], hold_days=20, cost=0.0021)
    gross = 100.0 / 90.0 - 1.0
    assert abs(t.ret_net - (gross - 0.0021)) < 1e-9
```

- [ ] **Step 2: 실패 확인**

Run: `cd LAB && python -m pytest tests/test_sim.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lab.sim'`

- [ ] **Step 3: 구현**

`LAB/lab/sim.py`:
```python
"""체결·청산 시뮬. 전략과 대조군이 이 함수를 공유한다."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from lab.bands import WEIGHTS


@dataclass
class Trade:
    code: str
    entry_date: str
    avg_cost: float
    exit_date: str
    exit_px: float
    ret_net: float
    filled_n: int
    truncated: bool


def simulate(bars: pd.DataFrame, levels, hold_days: int = 20,
             cost: float = 0.0021, code: str = "") -> Trade | None:
    """레벨을 순서대로 체결하고, 마지막 체결일 + hold_days 종가에 청산한다.

    ⚠️ 기산점(마지막 체결일)은 전략·대조군이 동일해야 한다.
       달리 잡으면 3차의 기한 비대칭이 재발한다.
    """
    w = WEIGHTS[: len(levels)]
    fills: list[tuple[float, float]] = []
    last_pos = None
    for pos in range(len(bars)):
        row = bars.iloc[pos]
        for i, lv in enumerate(levels):
            if i < len(fills):
                continue
            if row["open"] < lv:
                fills.append((float(row["open"]), w[i]))
                last_pos = pos
            elif row["low"] <= lv:
                fills.append((float(lv), w[i]))
                last_pos = pos
        if len(fills) == len(levels):
            break
    if not fills:
        return None

    tot_w = sum(x[1] for x in fills)
    avg_cost = sum(px * wi for px, wi in fills) / tot_w

    exit_pos = last_pos + hold_days
    truncated = exit_pos >= len(bars)
    if truncated:
        exit_pos = len(bars) - 1
    exit_row = bars.iloc[exit_pos]
    ret_net = float(exit_row["close"]) / avg_cost - 1.0 - cost

    return Trade(
        code=code,
        entry_date=str(bars.iloc[last_pos]["date"]),
        avg_cost=avg_cost,
        exit_date=str(exit_row["date"]),
        exit_px=float(exit_row["close"]),
        ret_net=ret_net,
        filled_n=len(fills),
        truncated=truncated,
    )
```

`LAB/lab/control.py`:
```python
"""대조군 — 진입 '가격'만 무작위. 비중·청산은 전략과 동일하게 붙는다."""
from __future__ import annotations

import numpy as np


def control_levels(peak: float, low_bound: float, rng: np.random.Generator, n: int = 5) -> list[float]:
    """[low_bound, peak] 구간에서 무작위 5개를 뽑아 내림차순으로 놓는다.

    전략과 같은 개수·같은 비중·같은 청산을 쓰므로,
    남는 차이는 '어느 가격에 걸었는가' 뿐이다.
    """
    px = rng.uniform(low_bound, peak, size=n)
    return sorted(px.tolist(), reverse=True)
```

- [ ] **Step 4: 통과 확인**

Run: `cd LAB && python -m pytest tests/test_sim.py -v`
Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
cd LAB && git add lab/sim.py lab/control.py tests/test_sim.py && git commit -q -m "feat(sim): 체결·청산 시뮬 + 대조군 진입가"
```

---

## Task 8: 통계 — Δ, t, White Reality Check, MDE

**Files:**
- Create: `LAB/lab/stats.py`
- Test: `LAB/tests/test_stats.py`

**Interfaces:**
- Produces:
  - `delta_t(strategy: np.ndarray, control: np.ndarray) -> tuple[float, float]`
  - `white_reality_check(cell_deltas: dict[str, np.ndarray], b: int = 1000, seed: int = 20260801) -> float`
  - `mde(n: int, sd: float, alpha: float = 0.05, power: float = 0.8) -> float`

- [ ] **Step 1: 실패 테스트 작성**

`LAB/tests/test_stats.py`:
```python
import numpy as np
from lab.stats import delta_t, mde, white_reality_check


def _panel(n_cells: int, n_codes: int, edge_cell: str | None = None, seed: int = 0):
    """셀 × 종목코드 패널. 같은 코드가 모든 셀에 등장해 블록 구조를 만든다."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_cells):
        cell = f"c{i}"
        mu = 0.04 if cell == edge_cell else 0.0
        for k in range(n_codes):
            for _ in range(4):
                rows.append({"cell": cell, "code": f"S{k:03d}", "d": rng.normal(mu, 0.05)})
    return pd.DataFrame(rows)


def test_reality_check_false_positive_rate_across_seeds():
    """귀무 하에서 거짓양성이 없어야 한다.

    단일 시드로 p>0.10 을 단언하면 안 된다 — 귀무 하에서 p 는 분포를 갖는다.
    """
    ps = [white_reality_check(_panel(20, 100, seed=s), b=200, seed=s + 100) for s in range(5)]
    assert sum(p < 0.05 for p in ps) == 0, ps


def test_reality_check_detects_a_genuinely_strong_cell():
    p = white_reality_check(_panel(20, 100, edge_cell="c7", seed=7), b=200, seed=1)
    assert p < 0.05, p


def test_reality_check_requires_a_code_column():
    """행 단위 리샘플링이면 유효표본을 거래 수로 착각한다 — 블록이어야 한다.

    code 컬럼을 요구하는 API 자체가 호출부에서 블록 구조를 강제한다.
    """
    import inspect
    assert "df" in inspect.signature(white_reality_check).parameters
    with pytest.raises(KeyError):
        white_reality_check(pd.DataFrame({"cell": ["a"], "d": [0.1]}), b=5)


def test_mde_shrinks_as_sample_grows():
    assert mde(n=400, sd=0.20) > mde(n=4000, sd=0.20)


def test_delta_is_strategy_minus_control():
    d, _ = delta_t(np.array([0.10, 0.10]), np.array([0.04, 0.04]))
    assert abs(d - 0.06) < 1e-12
```

- [ ] **Step 2: 실패 확인**

Run: `cd LAB && python -m pytest tests/test_stats.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lab.stats'`

- [ ] **Step 3: 구현**

`LAB/lab/stats.py`:
```python
"""판정 통계량. 사전등록된 규칙 외로 PASS 를 만들지 않는다."""
from __future__ import annotations

import numpy as np
from scipy import stats as sps


def delta_t(strategy: np.ndarray, control: np.ndarray) -> tuple[float, float]:
    """거래당 초과수익과 Welch t."""
    d = float(np.mean(strategy) - np.mean(control))
    t = float(sps.ttest_ind(strategy, control, equal_var=False).statistic)
    return d, t


def white_reality_check(df: pd.DataFrame, b: int = 1000, seed: int = 20260801) -> float:
    """max-t **종목코드 블록** 부트스트랩.

    입력 df 컬럼: `cell`, `code`, `d`(= 전략 수익률 − 대조군 수익률).
    귀무: 모든 셀의 기대 초과수익 = 0.

    ⚠️ 행 단위 독립 리샘플링을 쓰지 말 것. 같은 종목·같은 시기의 거래가
       셀 간에 겹치므로 유효표본은 거래 수가 아니라 **종목 수**다.
       1~3차도 종목코드 블록을 썼다 — 방법론이 달라지면 계열 비교가 깨진다.
       (참고: 상관 있는 귀무 구성 6회에서 두 방식 모두 거짓양성 0이었다.
        블록을 채택하는 근거는 거짓양성 실측이 아니라 계열 일관성이다.)

    부트스트랩 1회 = 종목코드를 복원추출로 뽑아 **모든 셀에 같은 코드 집합을
    적용**한다. 이래야 셀 간 의존구조가 보존된다.
    """
    rng = np.random.default_rng(seed)
    codes = df["code"].unique()
    cells = list(df["cell"].unique())
    # 셀 → 종목코드 → d 배열 (부트스트랩 루프에서 재계산하지 않도록 미리 접는다)
    per = {c: {k: g["d"].to_numpy() for k, g in df[df["cell"] == c].groupby("code")}
           for c in cells}
    full = {c: np.concatenate(list(per[c].values())) for c in cells}

    def _t(x: np.ndarray) -> float:
        if len(x) < 2:
            return 0.0
        se = np.std(x, ddof=1) / np.sqrt(len(x))
        return float(np.mean(x) / se) if se > 0 else 0.0

    obs_max = max(_t(full[c]) for c in cells)

    boot_max = np.empty(b)
    for j in range(b):
        pick = rng.choice(codes, size=len(codes), replace=True)   # 셀 전체에 같은 코드 집합
        stat = []
        for c in cells:
            parts = [per[c][k] for k in pick if k in per[c]]
            if not parts:
                stat.append(0.0)
                continue
            s = np.concatenate(parts)
            se = np.std(s, ddof=1) / np.sqrt(len(s)) if len(s) > 1 else 0.0
            stat.append((np.mean(s) - np.mean(full[c])) / se if se > 0 else 0.0)
        boot_max[j] = max(stat)
    return float((np.sum(boot_max >= obs_max) + 1) / (b + 1))


def mde(n: int, sd: float, alpha: float = 0.05, power: float = 0.8) -> float:
    """양측 alpha·주어진 power 에서 탐지 가능한 최소 평균차."""
    z_a = sps.norm.ppf(1 - alpha / 2)
    z_b = sps.norm.ppf(power)
    return float((z_a + z_b) * sd * np.sqrt(2.0 / n))
```

- [ ] **Step 4: 통과 확인**

Run: `cd LAB && python -m pytest tests/test_stats.py -v`
Expected: 4 passed

- [ ] **Step 5: MDE 를 산출하고 표본 게이트를 통과시킨다**

Task 6에서 나온 예상 표본수 N 과 거래당 수익률 표준편차 s 로 MDE 를 계산해 사전등록 §4 를 채운다.

실측 기준값(sd = 0.20 가정):

| 표본 N | MDE |
|---|---|
| 400 | **3.96%p** |
| 1,000 | 2.51%p |
| 4,000 | **1.25%p** |

⚠️ **표본 게이트.** 3차 결론이 "거래당 1.7%p 이상의 엣지 없음" 이었다. 이번 표본의 MDE 가 **1.7%p 보다 크면 4차는 3차보다 둔한 검정**이 되어, FAIL 이 나와도 새로 닫히는 게 없다. 그 경우 본실행 전에 멈추고 사장님께 보고한다 — 선택지는 (a) 유효기간 D 를 늘려 표본 확대 (b) 60분봉으로 전환해 표본 확대 (c) 검정 중단.

먼저 실제 s 를 재야 한다. Task 6 선정 정의로 segment 를 뽑아 **전략 팔만 소규모로 돌려 거래당 수익률 표준편차를 측정**하고(대조군·판정은 아직 계산하지 않는다), 그 s 로 MDE 를 확정한다.

- [ ] **Step 6: 커밋**

```bash
cd LAB && git add lab/stats.py tests/test_stats.py && git commit -q -m "feat(stats): Δ·t·White Reality Check·MDE"
```

---

## Task 9: 본실행과 산출물

**Files:**
- Create: `LAB/lab/run.py`
- Test: `LAB/tests/test_run_smoke.py`

**Interfaces:**
- Consumes: 전 모듈
- Produces: `LAB/out/` 아래 `trades.parquet`, `cells.csv`, `by_year.csv`, `by_bucket.csv`, `truncation.csv`, `verdict.json`

- [ ] **Step 1: 산출물 스키마 테스트 작성**

`LAB/tests/test_run_smoke.py`:
```python
from lab.run import required_outputs


def test_all_five_mandatory_artifacts_are_declared():
    """FAIL 이어도 이 다섯은 반드시 나온다 (사전등록 §5)."""
    names = set(required_outputs())
    assert {"by_year.csv", "truncation.csv", "cells.csv",
            "by_bucket.csv", "calibration_scores.csv"} <= names


def test_truncation_is_reported_for_both_arms():
    from lab.run import TRUNCATION_COLUMNS
    assert "strategy_truncated" in TRUNCATION_COLUMNS
    assert "control_truncated" in TRUNCATION_COLUMNS


def test_pit_gate_keeps_open_windows_out_of_history():
    """아직 창이 안 닫힌 표본이 분포에 새면 그게 look-ahead 다."""
    from lab.run import flush_pending
    pending = [("2026-03-01", 0.5, 0.2), ("2026-09-01", 0.6, 0.3)]
    ready, still = flush_pending(pending, as_of="2026-06-01")
    assert ready == [(0.5, 0.2)]
    assert still == [("2026-09-01", 0.6, 0.3)]


def test_pit_gate_is_inclusive_on_the_boundary_date():
    from lab.run import flush_pending
    ready, still = flush_pending([("2026-06-01", 0.5, 0.2)], as_of="2026-06-01")
    assert ready == [(0.5, 0.2)] and still == []


def test_control_seed_is_reproducible_across_processes():
    """내장 hash() 를 쓰면 실행마다 대조군이 달라져 증거가 못 된다."""
    from lab.run import _seed
    assert _seed("064260", "2026-07-23", "pit", 0.8) == _seed("064260", "2026-07-23", "pit", 0.8)
    assert _seed("064260", "2026-07-23", "pit", 0.8) != _seed("064260", "2026-07-23", "exo", 0.8)
```

- [ ] **Step 2: 실패 확인**

Run: `cd LAB && python -m pytest tests/test_run_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lab.run'`

- [ ] **Step 3: 구현**

`LAB/lab/run.py` 는 다음 순서로 돈다.

```python
"""본실행. 사전등록된 격자만 돈다."""
from __future__ import annotations

TRUNCATION_COLUMNS = (
    "cell", "strategy_trades", "strategy_truncated",
    "control_trades", "control_truncated",
)


def required_outputs() -> tuple[str, ...]:
    return (
        "trades.parquet", "cells.csv", "by_year.csv",
        "by_bucket.csv", "truncation.csv", "calibration_scores.csv",
        "verdict.json",
    )


import json
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from lab.bands import BUCKETS, exogenous_quantiles, ladder, pit_quantiles
from lab.control import control_levels
from lab.data import load_daily
from lab.segments import find_segments
from lab.sim import simulate
from lab.stats import delta_t, mde, white_reality_check

START, END = "2021-01-04", "2026-07-31"
HOLD, COST = 20, 0.0021
C_GRID = (0.6, 0.8, 1.0)
SEED = 20260801


def _seed(*parts) -> int:
    """재현 가능한 시드. 내장 hash() 는 실행마다 달라져 대조군이 재현되지 않는다."""
    return zlib.crc32("|".join(str(p) for p in parts).encode()) ^ SEED


def _bucket_name(gain: float) -> str:
    lo = 0.0
    for b in BUCKETS:
        if gain >= b:
            lo = b
    return f">={lo:.2f}"


def flush_pending(pending, as_of: str):
    """창이 닫힌 표본만 history 로 내보낸다. (ready, still_pending) 반환.

    ⚠️ 이 게이트가 PIT 판본의 전부다. 아직 창이 열려 있는 구간의
       실현 하락폭을 분포에 넣으면 미래를 보고 밴드를 그리는 것이 된다.
    """
    ready, still = [], []
    for end_date, gain, realized in pending:
        (ready.append((gain, realized)) if end_date <= as_of
         else still.append((end_date, gain, realized)))
    return ready, still


def main() -> None:
    out = Path("out")
    out.mkdir(exist_ok=True)
    bars = load_daily(START, END)
    by_code = {c: g.reset_index(drop=True) for c, g in bars.groupby("stock_code", sort=False)}
    selected = json.loads((out / "selected_definitions.json").read_text(encoding="utf-8"))

    rows = []
    for d in selected:
        segs = sorted(find_segments(bars, d["variant"], d["lookback"], d["min_gain"]),
                      key=lambda s: s.peak_date)
        history: list[tuple[float, float]] = []
        pending: list[tuple[str, float, float]] = []   # (창 종료일, gain, 실현 하락폭)

        for seg in segs:
            ready, pending = flush_pending(pending, as_of=seg.peak_date)   # PIT 게이트
            history.extend(ready)

            g = by_code[seg.code]
            idx = g.index[g["date"] == seg.peak_date]
            if len(idx) == 0:
                continue
            i_peak = int(idx[0])
            window = g.iloc[i_peak + 1: i_peak + 1 + d["valid_days"] + HOLD].reset_index(drop=True)
            if window.empty:
                continue

            for version in ("pit", "exo"):
                q = pit_quantiles(history, seg.gain) if version == "pit" else exogenous_quantiles(seg.gain)
                if q is None:                     # PIT 표본 부족 → 진입 금지
                    continue
                for c in C_GRID:
                    levels = ladder(seg.peak_px, q[0], q[1], c)
                    t_s = simulate(window, levels, HOLD, COST, seg.code)
                    if t_s is None:
                        continue
                    rng = np.random.default_rng(_seed(seg.code, seg.peak_date, version, c))
                    t_c = simulate(window, control_levels(seg.peak_px, min(levels), rng),
                                   HOLD, COST, seg.code)
                    if t_c is None:
                        continue
                    rows.append({
                        "cell": f'{d["name"]}|{version}|c{c}',
                        "code": seg.code, "peak_date": seg.peak_date,
                        "year": seg.peak_date[:4], "bucket": _bucket_name(seg.gain),
                        "gain": seg.gain,
                        "ret_s": t_s.ret_net, "ret_c": t_c.ret_net,
                        "trunc_s": t_s.truncated, "trunc_c": t_c.truncated,
                    })

            realized = 1.0 - float(window["low"].min()) / seg.peak_px
            pending.append((str(window["date"].iat[-1]), seg.gain, realized))

    df = pd.DataFrame(rows)
    df.to_parquet(out / "trades.parquet")
    df["d"] = df["ret_s"] - df["ret_c"]

    cell_rows = []
    for cell, grp in df.groupby("cell"):
        delta, t = delta_t(grp["ret_s"].to_numpy(), grp["ret_c"].to_numpy())
        cell_rows.append({"cell": cell, "n": len(grp), "n_codes": grp["code"].nunique(),
                          "delta": delta, "t": t,
                          "mean_s": grp["ret_s"].mean(), "mean_c": grp["ret_c"].mean()})
    pd.DataFrame(cell_rows).to_csv(out / "cells.csv", index=False)

    df.groupby("year")["d"].agg(["count", "mean"]).to_csv(out / "by_year.csv")
    df.groupby("bucket")["d"].agg(["count", "mean"]).to_csv(out / "by_bucket.csv")
    df.groupby("cell").agg(
        strategy_trades=("ret_s", "size"), strategy_truncated=("trunc_s", "sum"),
        control_trades=("ret_c", "size"), control_truncated=("trunc_c", "sum"),
    ).reset_index().to_csv(out / "truncation.csv", index=False)

    p = white_reality_check(df[["cell", "code", "d"]], b=1000, seed=SEED)
    sd = float(df["ret_s"].std(ddof=1))
    verdict = {"p": p, "n_trades": int(len(df)), "n_codes": int(df["code"].nunique()),
               "n_cells": int(df["cell"].nunique()), "sd": sd,
               "mde": mde(len(df), sd), "seed": SEED,
               "verdict": "PASS" if p < 0.05 else "FAIL"}
    (out / "verdict.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(verdict, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

⚠️ **PIT 게이트가 이 파일의 핵심이다.** `pending` → `history` 이동 조건이 `end_date <= seg.peak_date` 인 이유는, 아직 창이 열려 있는 구간의 실현 하락폭을 분포에 넣으면 미래를 보고 밴드를 그리는 것이 되기 때문이다. 이 조건을 `True` 로 바꾸면 결과가 좋아질 텐데, **그건 결함이지 개선이 아니다.**

⚠️ 대조군 시드는 `_seed()` 로 결정된다. 파이썬 내장 `hash()` 는 문자열에 대해 실행마다 달라져 대조군이 재현되지 않는다 — 재현 불가능한 대조군은 증거가 못 된다.

- [ ] **Step 4: 통과 확인**

Run: `cd LAB && python -m pytest tests/ -v`
Expected: 전체 통과. 실패 0.

- [ ] **Step 5: 본실행 1회**

Run: `cd LAB && python -m lab.run 2>&1 | tee out/run.log`
Expected: `out/` 에 7개 파일. `verdict.json` 에 `p`, `delta`, `n_cells`, `mde`, seed 가 들어 있다.

⚠️ **결과가 마음에 안 든다고 격자를 바꿔 재실행하지 않는다.** 재실행이 필요하면 사유를 사전등록 문서에 추가 기록하고 그 사실을 결과에 표기한다.

- [ ] **Step 6: 커밋**

```bash
cd LAB && git add -A && git commit -q -m "run: 태쏘 4차 본실행 1회 + 산출물 7종"
```

---

## Task 10: 결과 보고와 메모리 반영

**Files:**
- Create: `C:\Users\sttgp\.claude\projects\D--GIT-kis-trading-template\memory\changelog-2026-08-01-tasso-quantile-ladder-test.md`
- Modify: `memory/MEMORY.md` (인덱스 한 줄)

- [ ] **Step 1: 독립 검증을 먼저 받는다**

작성자 자신이 결과를 승인하지 않는다. `verifier` 또는 `critic` 에이전트에 `out/` 산출물과 사전등록 문서를 주고 다음을 확인시킨다.

1. 판정이 사전등록 규칙(WRC p<0.05)과 일치하는가
2. 양쪽 절단 건수가 비대칭이 아닌가 (3차 재발 여부)
3. 헤드라인 수치가 `out/` 원본 파일에서 그대로 나오는가
4. 연도 분해에서 2026 제외 시 결론이 뒤집히지 않는가

⚠️ 에이전트의 "통과" 자기보고를 머지게이트로 쓰지 않는다. 관리자가 `out/` 파일을 직접 연다.

- [ ] **Step 2: changelog 작성**

헤드라인 수치는 전부 `out/` 파일에서 인용한다. FAIL 이면 **"MDE 이상의 엣지 없음"** 으로 서술하고 MDE 값을 함께 적는다. 생존편향의 방향성(낙관)도 결론에 명시한다.

- [ ] **Step 3: MEMORY.md 인덱스 갱신**

Task 1에서 넣은 사전등록 줄을 결과 줄로 교체하거나 그 아래에 결과 줄을 붙인다. 계열이 종결되면 `ARCHIVE_INDEX.md#closed-tasso-series` 로 내린다.

- [ ] **Step 4: 사장님 승인 후 커밋**

```bash
git add docs/superpowers/specs/ docs/superpowers/plans/
git commit -m "docs(research): 태쏘 4차 검정 결과 — <PASS|FAIL>"
```

---

## Self-Review 기록

- **Spec 커버리지**: 설계 §1~§10 전부 태스크에 매핑됨. §9(범위 밖)는 의도적으로 태스크 없음.
- **부호 오류 재발 방지**: Task 5 Step 5에서 변이 주입으로 가드 판별력을 실측한다. 3차에서 "회귀 가드의 판별력은 변이 주입으로 실측하라"를 배웠다.
- **절단 비대칭**: Task 7 `simulate` 가 전략·대조군 공용이고, Task 9 `TRUNCATION_COLUMNS` 가 양쪽을 강제한다.
- **타입 일관성**: `Segment`(Task 4) → `ladder`(Task 5) → `simulate`(Task 7) → `delta_t`(Task 8) 시그니처 확인함. `WEIGHTS` 는 `bands.py` 단일 정의이며 `sim.py`·`calibrate.py` 가 import 한다.
