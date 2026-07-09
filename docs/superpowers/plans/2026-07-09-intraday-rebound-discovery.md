# 장중 급락 후 반등 발굴 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 상시수집 199종목의 분봉에서 "장중 급락 후 반등" 사례를 라벨링하고, 반등 직전 특징의 예측력을 인샘플/아웃샘플로 랭킹한다.

**Architecture:** 순수 함수 파이프라인. 종목-일 단위로 1분봉을 스트리밍 로드 → 리샘플 → 라벨/대조/MAE 계산 → 특징 계산 → parquet 적재. 그 위에서 랭킹과 모양 프로브를 돌린다. 라벨러와 특징 계산은 **한 종목-일의 DataFrame만** 받는다. 세션 경계 누수가 구조적으로 불가능해진다.

**Tech Stack:** Python 3.9+, pandas 2.2.3, numpy 2.0.2, pyarrow 21.0.0, scikit-learn 1.6.1, psycopg2. **새 의존성 추가 금지.**

## Global Constraints

- **라이브 코드 무접촉.** `core/` `bot/` `framework/` `api/` `strategies/` `collectors/` `db/` `runners/` `signals/` `lib/` `utils/` `tools/` 를 **수정하지 않는다.** 읽기만 한다. 신규 코드는 전부 `scripts/discovery/intraday_rebound/` 아래.
- **DB는 읽기 전용.** `SELECT`만. 어떤 테이블에도 쓰지 않는다.
- **분봉 SSOT = `robotrader` DB의 `minute_candles`.** (`kis_template.minute_candles`는 2026-06-23부터 1.3M행뿐이라 사용 금지.)
- **일간 컨텍스트 SSOT = `kis_template` DB의 `daily_prices`.** `adj_factor`를 곱하지 않는다 (close가 이미 조정됨).
- **날짜 형식 함정:** `minute_candles.trade_date` = `'YYYYMMDD'`, `daily_prices.date` = `'YYYY-MM-DD'`. 조인 전 반드시 정규화.
- **DB 접속:** host `127.0.0.1`, port **5433**, user `robotrader`, password `1234`.
- **결측봉을 만들지 않는다.** 리샘플 버킷 안에 1분봉이 하나도 없으면 그 봉은 존재하지 않는다. forward-fill 금지.
- **정규장만.** `09:00:00 <= datetime.time() <= 15:30:00`.
- **유니버스:** 상시수집 199종목 고정 (2025-04-01 이후 거래일의 90% 이상 수집).
- **기간:** 2025-04-01 ~ 2026-07-09. 인샘플 `~2026-01-31`, 아웃샘플 `2026-02-01~`.
- **테스트:** `pytest`. 신규 테스트는 `tests/discovery/intraday_rebound/` 아래. DB 접속이 필요한 테스트는 `@pytest.mark.integration`으로 표시하고 기본 스위트에서 제외한다.
- **작업 트리는 `D:/tmp/wt-intraday-rebound` 하나뿐이다.** 라이브 봇이 `D:\GIT\kis-trading-template`에서 매일 07:40에 기동한다. **그 트리를 읽지도 쓰지도 말고, 거기서 `cd`·`pytest`·`git checkout`을 실행하지 말 것.** 페이퍼 트레이딩 로그와 DB가 오염된다. 모든 명령은 `cd D:/tmp/wt-intraday-rebound/RoboTrader_template`에서 시작한다.
- **파이썬은 시스템 인터프리터**(`C:\Program Files (x86)\Microsoft Visual Studio\Shared\Python39_64\python.exe`). 워크트리에 venv가 없다. `python -m pytest`로 실행한다. pandas 2.2.3 / numpy 2.0.2 / sklearn 1.6.1 / pyarrow 21.0.0 / psycopg2 확인됨.
- `config/key.ini` 부재 경고가 import 시 출력되나 무해하다. 무시한다.
- **커밋은 각 Task 끝에서.** 브랜치 `feat/intraday-rebound-discovery`. push 금지 (사용자 승인 필요).

## 스펙 대비 변경 1건

스펙 8절은 k-Shape를 지정했으나 **`tslearn`이 미설치**이며 새 의존성을 추가하지 않는다. 또한 우리 시퀀스는 딥 드롭 봉에 앵커링되어 있어 k-Shape의 시프트 불변성이 오히려 정렬 정보를 버린다. **z-정규화 20차원 벡터에 대한 `sklearn.cluster.KMeans`(유클리드)로 대체한다.** 프로브의 목적(모양에 정보가 있는가)은 그대로다. Task 7에서 스펙 8절을 함께 수정한다.

## File Structure

```
scripts/discovery/intraday_rebound/
  __init__.py
  db.py            읽기 전용 커넥터 (dbname 명시). Task 1
  universe.py      상시수집 199종목 산출 + 캐시. Task 1
  resample.py      TimeFrameConverter 래핑 + amount/bar_count. Task 2
  labeler.py       라벨_고가/라벨_종가/대조_하락/MAE (한 종목-일). Task 3
  reproduce.py     2.2절 표를 정식 파이프라인으로 재현 (게이트). Task 4
  features.py      6개 묶음 특징 (한 종목-일). Task 5
  ranking.py       층화 AUC, 방향성 AUC, 날짜 블록 부트스트랩. Task 6
  shape_probe.py   z-정규화 + KMeans + ATR 병기. Task 7
  build_dataset.py 전체 종목-일 순회 → parquet. Task 8
  report.py        리포트 생성. Task 8

tests/discovery/intraday_rebound/
  __init__.py
  test_resample.py
  test_labeler.py
  test_features.py
  test_ranking.py
  test_shape_probe.py
```

`labeler.py`와 `features.py`는 순수 함수다. DB도 파일도 모른다. 한 종목-일의 봉 DataFrame과 컨텍스트 dict만 받는다. 이것이 세션 경계 누수를 구조적으로 막는 장치이자, 테스트를 쉽게 만드는 장치다.

---

### Task 1: 스캐폴딩 + 읽기 전용 커넥터 + 유니버스

**Files:**
- Create: `scripts/discovery/intraday_rebound/__init__.py`
- Create: `scripts/discovery/intraday_rebound/db.py`
- Create: `scripts/discovery/intraday_rebound/universe.py`
- Create: `tests/discovery/intraday_rebound/__init__.py`

**Interfaces:**
- Produces:
  - `db.read_sql(sql: str, params: tuple, dbname: str) -> pd.DataFrame`
  - `universe.load_universe(dbname: str = 'robotrader', start_date: str = '20250401', min_coverage: float = 0.9) -> list[str]` — 정렬된 종목코드 리스트. 캐시 없음(by design): 호출마다 DB를 다시 조회한다.

- [ ] **Step 1: 패키지 디렉토리와 `__init__.py` 생성**

```bash
cd D:/tmp/wt-intraday-rebound/RoboTrader_template
mkdir -p scripts/discovery/intraday_rebound/_cache
mkdir -p tests/discovery/intraday_rebound
printf '"""장중 급락 후 반등 발굴 (연구 전용, 라이브 무접촉)."""\n' > scripts/discovery/intraday_rebound/__init__.py
printf '' > tests/discovery/intraday_rebound/__init__.py
printf '_cache/\n' > scripts/discovery/intraday_rebound/.gitignore
```

- [ ] **Step 2: `db.py` 작성**

`DatabaseConnection`을 쓰지 않는다. 그것은 `TIMESCALE_DB` 환경변수를 따라 `kis_template`로 붙으며, 우리는 분봉을 `robotrader`에서 읽어야 한다. 명시적 dbname을 받는 전용 커넥터를 쓴다.

```python
# scripts/discovery/intraday_rebound/db.py
"""읽기 전용 DB 커넥터. dbname을 명시적으로 받는다.

라이브 db.connection.DatabaseConnection은 TIMESCALE_DB env를 따라가므로
이 연구에서는 사용하지 않는다 (분봉 SSOT는 robotrader, 일봉은 kis_template).
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import pandas as pd
import psycopg2

DB_HOST = os.getenv("REBOUND_DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("REBOUND_DB_PORT", "5433"))
DB_USER = os.getenv("REBOUND_DB_USER", "robotrader")
DB_PASSWORD = os.getenv("REBOUND_DB_PASSWORD", "1234")

MINUTE_DB = "robotrader"
DAILY_DB = "kis_template"


@contextmanager
def connect(dbname: str):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, dbname=dbname,
    )
    try:
        conn.set_session(readonly=True, autocommit=True)
        yield conn
    finally:
        conn.close()


def read_sql(sql: str, params: tuple, dbname: str) -> pd.DataFrame:
    """SELECT 실행 후 DataFrame 반환. 쓰기 불가 세션."""
    with connect(dbname) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        cur.close()
    return pd.DataFrame(rows, columns=cols)
```

`conn.set_session(readonly=True)`가 이 모듈이 프로덕션 DB에 쓰지 못한다는 **기계적 보증**이다.

- [ ] **Step 3: 읽기 전용 세션이 쓰기를 거부하는지 확인**

```bash
cd D:/tmp/wt-intraday-rebound/RoboTrader_template
python -c "
from scripts.discovery.intraday_rebound import db
import psycopg2
with db.connect('robotrader') as c:
    cur = c.cursor()
    try:
        cur.execute('CREATE TEMP TABLE _probe(x int)')
        print('FAIL: write allowed')
    except psycopg2.Error as e:
        print('OK: write rejected ->', type(e).__name__)
"
```
Expected: `OK: write rejected -> ReadOnlySqlTransaction`

- [ ] **Step 4: `universe.py` 작성**

```python
# scripts/discovery/intraday_rebound/universe.py
"""상시수집 유니버스 산출 (2025-04-01 이후 거래일의 min_coverage 이상 수집).

캐시하지 않는다 — by design. 쿼리 결과는 dbname/start_date/min_coverage 뿐 아니라
minute_candles 에 쌓인 거래일 총수에도 의존하는데, 이 총수는 매일 늘어난다. 같은
파라미터라도 나중에 호출하면 커버리지 멤버십이 달라질 수 있어, 캐시된 유니버스가
아무 신호 없이 조용히 stale 해진다 (이 프로젝트가 오늘 겪은 운영 사고와 동일한
실패 형태). load_universe() 는 호출마다 DB를 다시 조회한다. 파이프라인 1회 실행당
~1회만 호출되며, 인덱스 스캔에 걸린 199행은 비용이 무시할 만하다.
"""
from __future__ import annotations

from .db import MINUTE_DB, read_sql

_SQL = """
WITH tot AS (
    SELECT COUNT(DISTINCT trade_date) AS d
    FROM minute_candles WHERE trade_date >= %s
),
per AS (
    SELECT stock_code, COUNT(DISTINCT trade_date) AS d
    FROM minute_candles WHERE trade_date >= %s
    GROUP BY stock_code
)
SELECT per.stock_code
FROM per, tot
WHERE per.d >= tot.d * %s
ORDER BY per.stock_code
"""


def load_universe(dbname: str = MINUTE_DB,
                  start_date: str = "20250401",
                  min_coverage: float = 0.9) -> list[str]:
    df = read_sql(_SQL, (start_date, start_date, min_coverage), dbname)
    return sorted(df["stock_code"].tolist())
```

- [ ] **Step 5: 유니버스가 199종목인지 확인 (스펙 2.1절 재현)**

```bash
cd D:/tmp/wt-intraday-rebound/RoboTrader_template
python -c "
from scripts.discovery.intraday_rebound.universe import load_universe
codes = load_universe()
print('count =', len(codes))
print('first5 =', codes[:5])
assert len(codes) == 199, f'expected 199, got {len(codes)}'
print('OK')
"
```
Expected: `count = 199` 다음 `OK`.

199가 아니면 **멈추고 보고한다.** 스펙 2.1절이 199를 근거로 쓰였으므로, 숫자가 다르면 수집이 진행되어 커버리지가 변했다는 뜻이고 스펙을 갱신해야 한다.

- [ ] **Step 6: 커밋**

```bash
cd D:/tmp/wt-intraday-rebound
git add RoboTrader_template/scripts/discovery/intraday_rebound/ RoboTrader_template/tests/discovery/intraday_rebound/
git commit -m "feat(discovery): 반등 발굴 스캐폴딩 + 읽기전용 커넥터 + 유니버스 산출"
```

---

### Task 2: 리샘플 어댑터

**Files:**
- Create: `scripts/discovery/intraday_rebound/resample.py`
- Test: `tests/discovery/intraday_rebound/test_resample.py`

**Interfaces:**
- Consumes: 없음 (순수 함수)
- Produces: `resample.resample_ohlcv(minute_df: pd.DataFrame, timeframe_minutes: int) -> pd.DataFrame`
  - 입력 컬럼: `datetime, open, high, low, close, volume, amount`
  - 출력 컬럼: `datetime, open, high, low, close, volume, amount, bar_count`
  - 빈 버킷은 행을 만들지 않는다.

**설계 근거.** 라이브 `core.timeframe_converter.TimeFrameConverter.convert_to_timeframe`는 OHLCV만 다루고 `amount`를 버린다. 우리는 거래대금 특징이 필요하다. 또 입력 전체 길이가 `timeframe_minutes`보다 짧으면 `None`을 반환하는데, 우리는 부분 버킷도 봉으로 쳐야 한다(거래 없는 분이 흔하다).

그래서 `groupby(datetime.floor(f'{n}min'))` **한 벌**로 직접 구현한다. 위임 + 폴백 두 벌을 두면 두 경로가 언젠가 어긋난다. 대신 **라이브 변환기와 결과가 같은지 검증하는 테스트**(`test_matches_live_converter_on_a_full_session`)를 둔다. 중복 없이 드리프트를 감시한다. pandas `resample`의 기본 `origin='start_day'`는 `floor`와 동일한 경계를 만들므로 두 구현의 OHLCV는 일치해야 한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/discovery/intraday_rebound/test_resample.py
import pandas as pd
import pytest

from scripts.discovery.intraday_rebound.resample import resample_ohlcv


def _minute_df(rows):
    """rows: list of (HH:MM, o, h, l, c, vol, amt)"""
    return pd.DataFrame([
        {
            "datetime": pd.Timestamp(f"2026-06-01 {t}:00"),
            "open": o, "high": h, "low": lo, "close": c,
            "volume": v, "amount": a,
        }
        for (t, o, h, lo, c, v, a) in rows
    ])


def test_three_minute_bucket_aggregates_ohlcv_amount_and_count():
    df = _minute_df([
        ("09:00", 100, 105, 99, 104, 10, 1000),
        ("09:01", 104, 110, 103, 108, 20, 2000),
        ("09:02", 108, 109, 101, 102, 30, 3000),
    ])
    out = resample_ohlcv(df, 3)

    assert len(out) == 1
    row = out.iloc[0]
    assert row["datetime"] == pd.Timestamp("2026-06-01 09:00:00")
    assert row["open"] == 100
    assert row["high"] == 110
    assert row["low"] == 99
    assert row["close"] == 102
    assert row["volume"] == 60
    assert row["amount"] == 6000
    assert row["bar_count"] == 3


def test_missing_minutes_do_not_create_bars():
    """09:03~09:05 구간에 1분봉이 없으면 그 3분봉은 존재하지 않는다 (ffill 금지)."""
    df = _minute_df([
        ("09:00", 100, 100, 100, 100, 1, 100),
        ("09:01", 100, 100, 100, 100, 1, 100),
        ("09:02", 100, 100, 100, 100, 1, 100),
        # 09:03, 09:04, 09:05 없음
        ("09:06", 200, 200, 200, 200, 1, 200),
        ("09:07", 200, 200, 200, 200, 1, 200),
        ("09:08", 200, 200, 200, 200, 1, 200),
    ])
    out = resample_ohlcv(df, 3)

    assert len(out) == 2
    assert list(out["datetime"]) == [
        pd.Timestamp("2026-06-01 09:00:00"),
        pd.Timestamp("2026-06-01 09:06:00"),
    ]
    assert out["close"].tolist() == [100, 200]


def test_partial_bucket_keeps_bar_with_lower_bar_count():
    """버킷에 1분봉이 일부만 있으면 봉은 생기되 bar_count가 3 미만이다."""
    df = _minute_df([
        ("09:00", 100, 101, 99, 100, 5, 500),
        ("09:02", 100, 103, 100, 103, 5, 500),
    ])
    out = resample_ohlcv(df, 3)

    assert len(out) == 1
    assert out.iloc[0]["bar_count"] == 2
    assert out.iloc[0]["high"] == 103


def test_fifteen_minute_bucket_boundaries_align_to_clock():
    rows = [(f"09:{m:02d}", 100, 100, 100, 100, 1, 10) for m in range(0, 30)]
    out = resample_ohlcv(_minute_df(rows), 15)
    assert list(out["datetime"]) == [
        pd.Timestamp("2026-06-01 09:00:00"),
        pd.Timestamp("2026-06-01 09:15:00"),
    ]


def test_empty_input_returns_empty_frame_with_columns():
    out = resample_ohlcv(pd.DataFrame(columns=[
        "datetime", "open", "high", "low", "close", "volume", "amount"
    ]), 3)
    assert out.empty
    assert "bar_count" in out.columns


@pytest.mark.parametrize("tf", [3, 5, 15])
def test_matches_live_converter_on_a_full_session(tf):
    """드리프트 감시: 우리 구현의 OHLCV 는 라이브 TimeFrameConverter 와 같아야 한다.

    리샘플 로직을 두 벌 두지 않는 대신, 두 구현이 어긋나면 여기서 잡는다.
    """
    from core.timeframe_converter import TimeFrameConverter

    rng = np.random.default_rng(0)
    n = 390                                   # 09:00~15:29 정규장 1분봉
    close = 10000 + np.cumsum(rng.normal(0, 5, n))
    df = pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=n, freq="1min"),
        "open": close + rng.normal(0, 1, n),
        "high": close + rng.uniform(0, 10, n),
        "low": close - rng.uniform(0, 10, n),
        "close": close,
        "volume": rng.integers(1, 1000, n).astype(float),
        "amount": rng.integers(1, 10**6, n).astype(float),
    })

    ours = resample_ohlcv(df, tf)
    theirs = TimeFrameConverter.convert_to_timeframe(df, tf)

    pd.testing.assert_frame_equal(
        ours[["datetime", "open", "high", "low", "close", "volume"]]
            .reset_index(drop=True),
        theirs[["datetime", "open", "high", "low", "close", "volume"]]
            .reset_index(drop=True),
        check_dtype=False,
    )
```

`import numpy as np`를 테스트 파일 상단에 추가한다.

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd D:/tmp/wt-intraday-rebound/RoboTrader_template && python -m pytest tests/discovery/intraday_rebound/test_resample.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.discovery.intraday_rebound.resample'`

- [ ] **Step 3: `resample.py` 구현**

```python
# scripts/discovery/intraday_rebound/resample.py
"""1분봉 → N분봉 리샘플.

버킷 경계는 datetime.floor(f'{n}min'). 빈 버킷은 행을 만들지 않는다 (ffill 금지).
라이브 TimeFrameConverter 와 OHLCV 가 일치하는지는
tests/.../test_resample.py::test_matches_live_converter_on_a_full_session 이 감시한다.
"""
from __future__ import annotations

import pandas as pd

OUT_COLUMNS = ["datetime", "open", "high", "low", "close", "volume", "amount", "bar_count"]


def resample_ohlcv(minute_df: pd.DataFrame, timeframe_minutes: int) -> pd.DataFrame:
    if minute_df is None or minute_df.empty:
        return pd.DataFrame(columns=OUT_COLUMNS)

    df = minute_df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"])
    bucket = df["datetime"].dt.floor(f"{timeframe_minutes}min")

    out = df.groupby(bucket, sort=True).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        amount=("amount", "sum"),
        bar_count=("close", "size"),
    ).reset_index()
    out.columns = OUT_COLUMNS
    return out
```

`groupby`는 존재하는 버킷만 만든다. 빈 3분 구간에 대해 행이 생기지 않으므로 forward-fill 함정이 원천 차단된다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd D:/tmp/wt-intraday-rebound/RoboTrader_template && python -m pytest tests/discovery/intraday_rebound/test_resample.py -v`
Expected: 8 passed (5 + 파라미터화된 드리프트 감시 3)

`test_matches_live_converter_on_a_full_session`이 실패하면 **버킷 경계가 어긋난 것이다.** 우리 `floor`와 pandas `resample(origin='start_day')`가 다른 결과를 냈다는 뜻이므로, 리샘플러를 고치기 전에 어느 쪽이 옳은지 먼저 판단한다.

- [ ] **Step 5: 커밋**

```bash
cd D:/tmp/wt-intraday-rebound
git add RoboTrader_template/scripts/discovery/intraday_rebound/resample.py RoboTrader_template/tests/discovery/intraday_rebound/test_resample.py
git commit -m "feat(discovery): 리샘플 어댑터 (amount/bar_count 추가, 빈 버킷 미생성)"
```

---

### Task 3: 라벨러

**Files:**
- Create: `scripts/discovery/intraday_rebound/labeler.py`
- Test: `tests/discovery/intraday_rebound/test_labeler.py`

**Interfaces:**
- Consumes: `resample.resample_ohlcv` 출력 스키마
- Produces:
  ```python
  labeler.LabelParams(timeframe_minutes: int, lookback_min: int, drop_pct: float,
                      forward_min: int, theta: float)
  labeler.compute_labels(bars: pd.DataFrame, params: LabelParams) -> pd.DataFrame
  ```
  출력 컬럼 (입력 봉과 동일 길이, 동일 순서):
  `prior_high, drop_pct_actual, is_candidate, hit_up, hit_down, hit_close, mae, forward_bars`

**정의 (스펙 5절)**

- `L = lookback_min // timeframe_minutes` 봉, `F = forward_min // timeframe_minutes` 봉
- `prior_high[t] = max(high[t-L .. t-1])` — 자기 봉 제외
- `is_candidate[t] = close[t] <= prior_high[t] * (1 - drop_pct)`
- `hit_up[t]`: `t+1..t+F` 중 `high >= close[t] * (1+theta)`
- `hit_down[t]`: `t+1..t+F` 중 `low <= close[t] * (1-theta)` (독립 측정)
- `hit_close[t]`: `close[t+F] >= close[t] * (1+theta)`
- `mae[t]`: `t+1`부터 `hit_up` 발생 봉까지(포함), 미발생 시 `t+F`까지의 `min(low) / close[t] - 1`

**bars는 한 종목-일이다.** 윈도우가 세션을 넘을 수 없다. 창이 모자라면(`t+F`가 당일 마지막 봉을 넘으면) `is_candidate=False`로 만들지 말고 `forward_bars`에 실제 남은 봉 수를 기록하되, `hit_close`는 `NaN`으로 둔다. `hit_up`/`hit_down`/`mae`는 남은 봉으로 계산한다 — 반등이 이미 발생했다면 그것은 사실이므로 버리지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/discovery/intraday_rebound/test_labeler.py
import numpy as np
import pandas as pd
import pytest

from scripts.discovery.intraday_rebound.labeler import LabelParams, compute_labels


def _bars(closes, highs=None, lows=None):
    n = len(closes)
    highs = highs if highs is not None else closes
    lows = lows if lows is not None else closes
    return pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=n, freq="3min"),
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [1] * n,
        "amount": [1] * n,
        "bar_count": [3] * n,
    })


P = LabelParams(timeframe_minutes=3, lookback_min=6, drop_pct=0.025,
                forward_min=6, theta=0.03)
# L = 2 bars, F = 2 bars


def test_prior_high_excludes_current_bar():
    bars = _bars([100, 110, 100, 100, 100])
    out = compute_labels(bars, P)
    # t=2 의 prior_high 는 t=0,1 의 high 최대 = 110
    assert out.loc[2, "prior_high"] == 110
    # t=0 은 룩백 없음
    assert np.isnan(out.loc[0, "prior_high"])


def test_candidate_requires_drop_below_threshold():
    # prior_high=110, close=107.25 → drop 2.5% 정확히 → 후보 (<=)
    bars = _bars([100, 110, 107.25, 100, 100])
    out = compute_labels(bars, P)
    assert bool(out.loc[2, "is_candidate"]) is True

    # close=108 → drop 1.8% → 후보 아님
    bars2 = _bars([100, 110, 108, 100, 100])
    out2 = compute_labels(bars2, P)
    assert bool(out2.loc[2, "is_candidate"]) is False


def test_hit_up_uses_forward_high_within_window():
    # t=2 close=100, theta=3% → target 103
    # t=3 high=103 → hit_up True
    bars = _bars(closes=[100, 110, 100, 101, 101],
                 highs=[100, 110, 100, 103, 101],
                 lows=[100, 110, 100, 101, 101])
    out = compute_labels(bars, P)
    assert bool(out.loc[2, "hit_up"]) is True


def test_hit_up_false_when_touch_is_outside_window():
    # F=2 → t=2 의 창은 t=3, t=4. t=5 의 고가는 무시돼야 한다.
    bars = _bars(closes=[100, 110, 100, 101, 101, 101],
                 highs=[100, 110, 100, 101, 101, 200],
                 lows=[100, 110, 100, 101, 101, 101])
    out = compute_labels(bars, P)
    assert bool(out.loc[2, "hit_up"]) is False


def test_hit_down_measured_independently_of_hit_up():
    # t=2 close=100. t=3 low=96 (-4% → hit_down), t=4 high=104 (+4% → hit_up)
    bars = _bars(closes=[100, 110, 100, 100, 100],
                 highs=[100, 110, 100, 100, 104],
                 lows=[100, 110, 100, 96, 100])
    out = compute_labels(bars, P)
    assert bool(out.loc[2, "hit_up"]) is True
    assert bool(out.loc[2, "hit_down"]) is True


def test_mae_stops_at_the_bar_that_hits_up():
    # t=2 close=100. t=3: low=98 (mae -2%), high=103 → hit. t=4 low=50 는 무시.
    bars = _bars(closes=[100, 110, 100, 100, 100],
                 highs=[100, 110, 100, 103, 100],
                 lows=[100, 110, 100, 98, 50])
    out = compute_labels(bars, P)
    assert out.loc[2, "hit_up"]
    assert out.loc[2, "mae"] == pytest.approx(-0.02)


def test_mae_uses_full_window_when_never_hits():
    bars = _bars(closes=[100, 110, 100, 100, 100],
                 highs=[100, 110, 100, 100, 100],
                 lows=[100, 110, 100, 99, 97])
    out = compute_labels(bars, P)
    assert not out.loc[2, "hit_up"]
    assert out.loc[2, "mae"] == pytest.approx(-0.03)


def test_hit_close_uses_bar_at_t_plus_F():
    # F=2 → t=2 의 hit_close 는 close[4] 로 판정. close[4]=103 → True
    bars = _bars([100, 110, 100, 200, 103])
    out = compute_labels(bars, P)
    assert bool(out.loc[2, "hit_close"]) is True


def test_truncated_window_at_session_end_sets_hit_close_nan():
    # 마지막 봉 t=4 는 앞으로 봉이 없다
    bars = _bars([100, 110, 100, 100, 100])
    out = compute_labels(bars, P)
    assert out.loc[4, "forward_bars"] == 0
    assert np.isnan(out.loc[4, "hit_close"])
    assert bool(out.loc[4, "hit_up"]) is False


def test_no_window_crosses_session_boundary_because_input_is_one_day():
    """계약 확인: compute_labels 는 한 종목-일만 받는다. 길이 보존."""
    bars = _bars([100] * 10)
    out = compute_labels(bars, P)
    assert len(out) == len(bars)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd D:/tmp/wt-intraday-rebound/RoboTrader_template && python -m pytest tests/discovery/intraday_rebound/test_labeler.py -v`
Expected: FAIL — `ModuleNotFoundError: ... labeler`

- [ ] **Step 3: `labeler.py` 구현**

```python
# scripts/discovery/intraday_rebound/labeler.py
"""라벨/대조/MAE 계산. 입력은 반드시 한 종목-일의 봉이다.

세션 경계 누수는 입력 계약으로 막는다 (한 종목-일만 받으므로 창이 넘어갈 수 없다).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

OUT_COLUMNS = [
    "prior_high", "drop_pct_actual", "is_candidate",
    "hit_up", "hit_down", "hit_close", "mae", "forward_bars",
]


@dataclass(frozen=True)
class LabelParams:
    timeframe_minutes: int
    lookback_min: int
    drop_pct: float
    forward_min: int
    theta: float

    @property
    def lookback_bars(self) -> int:
        return max(1, self.lookback_min // self.timeframe_minutes)

    @property
    def forward_bars(self) -> int:
        return max(1, self.forward_min // self.timeframe_minutes)


def compute_labels(bars: pd.DataFrame, params: LabelParams) -> pd.DataFrame:
    n = len(bars)
    if n == 0:
        return pd.DataFrame(columns=OUT_COLUMNS)

    L = params.lookback_bars
    F = params.forward_bars
    theta = params.theta

    high = bars["high"].to_numpy(dtype=float)
    low = bars["low"].to_numpy(dtype=float)
    close = bars["close"].to_numpy(dtype=float)

    prior_high = (
        pd.Series(high).rolling(L, min_periods=L).max().shift(1).to_numpy()
    )

    with np.errstate(invalid="ignore", divide="ignore"):
        drop_actual = close / prior_high - 1.0
    is_candidate = drop_actual <= -params.drop_pct

    hit_up = np.zeros(n, dtype=bool)
    hit_down = np.zeros(n, dtype=bool)
    hit_close = np.full(n, np.nan)
    mae = np.full(n, np.nan)
    fwd_bars = np.zeros(n, dtype=int)

    for t in range(n):
        end = min(t + F, n - 1)
        fwd_bars[t] = end - t
        if end <= t:
            continue

        up_target = close[t] * (1.0 + theta)
        dn_target = close[t] * (1.0 - theta)

        running_min = np.inf
        hit_idx = -1
        for j in range(t + 1, end + 1):
            running_min = min(running_min, low[j])
            if high[j] >= up_target:
                hit_idx = j
                break

        if hit_idx >= 0:
            hit_up[t] = True
            mae[t] = running_min / close[t] - 1.0
        else:
            mae[t] = np.min(low[t + 1:end + 1]) / close[t] - 1.0

        hit_down[t] = bool(np.min(low[t + 1:end + 1]) <= dn_target)

        if t + F <= n - 1:
            hit_close[t] = float(close[t + F] >= up_target)

    return pd.DataFrame({
        "prior_high": prior_high,
        "drop_pct_actual": drop_actual,
        "is_candidate": is_candidate,
        "hit_up": hit_up,
        "hit_down": hit_down,
        "hit_close": hit_close,
        "mae": mae,
        "forward_bars": fwd_bars,
    })
```

`mae`는 첫 `hit_up` 봉에서 멈춘다. `hit_down`은 창 전체를 본다 — 스펙 2.2절이 두 도달률을 **독립적으로** 측정했기 때문이다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd D:/tmp/wt-intraday-rebound/RoboTrader_template && python -m pytest tests/discovery/intraday_rebound/test_labeler.py -v`
Expected: 10 passed

- [ ] **Step 5: 커밋**

```bash
cd D:/tmp/wt-intraday-rebound
git add RoboTrader_template/scripts/discovery/intraday_rebound/labeler.py RoboTrader_template/tests/discovery/intraday_rebound/test_labeler.py
git commit -m "feat(discovery): 라벨러 (hit_up/hit_down/hit_close/MAE, 첫 도달에서 MAE 절단)"
```

---

### Task 3b: 룩백 세그먼트 도입 (Task 4 게이트 결과 반영)

Task 4 게이트가 최초 스펙 2.2절 표의 오류를 잡아냈다. `rolling(min_periods=L)`이 개장 직후 `L`봉을 NaN으로 만들어 **딥 드롭 이벤트의 46%를 버리고 있었다.** 그렇다고 `min_periods=1`로 낮추면 09:03 봉의 "직전 60분 고점"이 실제로는 직전 3분 고점이 되어, 같은 `−4% 하락` 라벨이 시간대마다 다른 것을 뜻하게 된다.

**해법: 버리지도 섞지도 않는다.** 짧은 룩백을 허용하되 그 사실을 컬럼으로 드러내고, 모든 통계를 세그먼트별로 분리한다.

**Files:**
- Modify: `scripts/discovery/intraday_rebound/labeler.py`
- Modify: `tests/discovery/intraday_rebound/test_labeler.py`

**Interfaces (변경):**
```python
LabelParams(timeframe_minutes, lookback_min, drop_pct, forward_min, theta,
            min_lookback_min: int = 15)
LabelParams.min_lookback_bars -> max(1, min_lookback_min // timeframe_minutes)
```
`compute_labels` 출력에 두 컬럼 추가:
- `lookback_bars_used`: `min(t, L)` — 실제로 쓰인 앞 봉 개수
- `is_full_lookback`: `lookback_bars_used == L`

기존 8개 컬럼과 길이·순서는 그대로. `prior_high`는 이제 `min_periods=min_lookback_bars`로 계산한다.

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/discovery/intraday_rebound/test_labeler.py`에 추가한다. 기존 10개 테스트는 건드리지 않는다 — 단, 기존 `P`는 `min_lookback_min` 기본값 15를 받으므로 `timeframe_minutes=3`에서 `min_lookback_bars=5`가 되어 `t<5`의 `prior_high`가 NaN이 된다. 기존 테스트는 `t=2`에서 `prior_high`를 검사하므로 **깨진다.** 기존 테스트의 `P`를 `LabelParams(..., min_lookback_min=6)`로 바꿔 `min_lookback_bars=2`가 되게 하라 (L=2와 같아져 기존 기대값이 유지된다).

```python
def test_min_lookback_bars_derived_from_timeframe():
    p = LabelParams(timeframe_minutes=3, lookback_min=60, drop_pct=0.04,
                    forward_min=60, theta=0.03)
    assert p.lookback_bars == 20
    assert p.min_lookback_bars == 5          # 15분 // 3분

    p15 = LabelParams(timeframe_minutes=15, lookback_min=60, drop_pct=0.04,
                      forward_min=60, theta=0.03)
    assert p15.min_lookback_bars == 1        # max(1, 15 // 15)


def test_prior_high_uses_partial_window_after_min_lookback():
    """min_lookback_bars 이후에는 앞 봉이 L개 미만이어도 prior_high 를 낸다."""
    p = LabelParams(timeframe_minutes=3, lookback_min=30, drop_pct=0.025,
                    forward_min=6, theta=0.03, min_lookback_min=6)
    # L = 10 bars, min_lookback = 2 bars
    bars = _bars([100, 110, 105, 100, 100, 100])
    out = compute_labels(bars, p)

    assert np.isnan(out.loc[0, "prior_high"])       # 앞 봉 0개
    assert np.isnan(out.loc[1, "prior_high"])       # 앞 봉 1개 < min 2
    assert out.loc[2, "prior_high"] == 110          # 앞 봉 2개, 부분 룩백
    assert out.loc[3, "prior_high"] == 110          # 앞 봉 3개


def test_lookback_bars_used_counts_actual_preceding_bars():
    p = LabelParams(timeframe_minutes=3, lookback_min=9, drop_pct=0.025,
                    forward_min=6, theta=0.03, min_lookback_min=3)
    # L = 3 bars
    bars = _bars([100] * 6)
    out = compute_labels(bars, p)
    assert out["lookback_bars_used"].tolist() == [0, 1, 2, 3, 3, 3]


def test_is_full_lookback_true_only_when_window_is_complete():
    p = LabelParams(timeframe_minutes=3, lookback_min=9, drop_pct=0.025,
                    forward_min=6, theta=0.03, min_lookback_min=3)
    bars = _bars([100] * 6)
    out = compute_labels(bars, p)
    assert out["is_full_lookback"].tolist() == [False, False, False, True, True, True]


def test_partial_lookback_bar_can_be_a_candidate():
    """개장 직후 급락이 후보로 살아남아야 한다 (46% 데이터 손실 방지)."""
    p = LabelParams(timeframe_minutes=3, lookback_min=60, drop_pct=0.04,
                    forward_min=6, theta=0.03)      # L=20, min=5
    closes = [100, 100, 100, 100, 100, 95, 95, 95]  # t=5 에서 -5%
    bars = _bars(closes)
    out = compute_labels(bars, p)

    assert bool(out.loc[5, "is_candidate"]) is True
    assert bool(out.loc[5, "is_full_lookback"]) is False
    assert out.loc[5, "lookback_bars_used"] == 5
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd D:/tmp/wt-intraday-rebound/RoboTrader_template && python -m pytest tests/discovery/intraday_rebound/test_labeler.py -v`
Expected: 새 테스트 5개가 실패 (`TypeError: __init__() got an unexpected keyword argument 'min_lookback_min'` 등)

- [ ] **Step 3: `labeler.py` 수정**

```python
OUT_COLUMNS = [
    "prior_high", "drop_pct_actual", "is_candidate",
    "hit_up", "hit_down", "hit_close", "mae", "forward_bars",
    "lookback_bars_used", "is_full_lookback",
]


@dataclass(frozen=True)
class LabelParams:
    timeframe_minutes: int
    lookback_min: int
    drop_pct: float
    forward_min: int
    theta: float
    min_lookback_min: int = 15

    @property
    def lookback_bars(self) -> int:
        return max(1, self.lookback_min // self.timeframe_minutes)

    @property
    def forward_bars(self) -> int:
        return max(1, self.forward_min // self.timeframe_minutes)

    @property
    def min_lookback_bars(self) -> int:
        return max(1, self.min_lookback_min // self.timeframe_minutes)
```

`compute_labels` 안에서 `prior_high` 계산을 바꾸고 두 컬럼을 추가한다.

```python
    L = params.lookback_bars
    prior_high = (
        pd.Series(high)
        .rolling(L, min_periods=params.min_lookback_bars)
        .max()
        .shift(1)
        .to_numpy()
    )

    lookback_used = np.minimum(np.arange(n), L)
    is_full = lookback_used == L
    # min_lookback 미만 구간은 prior_high 가 NaN 이므로 is_candidate 가 False 가 된다.
```

반환 DataFrame에 `"lookback_bars_used": lookback_used, "is_full_lookback": is_full`를 추가한다. 나머지 로직은 **한 줄도 바꾸지 않는다.**

주의: `rolling(...).shift(1)`이므로 `prior_high[t]`는 앞 봉 `min(t, L)`개를 본다. `lookback_used[t] = min(t, L)`이 그것과 정확히 일치한다. `min_periods` 때문에 `t < min_lookback_bars`인 행은 NaN이고, 그 행의 `lookback_bars_used`는 여전히 `t`를 기록한다(정보 손실 방지).

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd D:/tmp/wt-intraday-rebound/RoboTrader_template && python -m pytest tests/discovery/intraday_rebound/ -v`
Expected: 26 passed (11 리샘플 + 15 라벨러)

- [ ] **Step 5: 커밋**

```bash
cd D:/tmp/wt-intraday-rebound
git add RoboTrader_template/scripts/discovery/intraday_rebound/labeler.py RoboTrader_template/tests/discovery/intraday_rebound/test_labeler.py
git commit -m "feat(discovery): 룩백 세그먼트 (lookback_bars_used/is_full_lookback)"
```

---

### Task 4: 재현 게이트 — 스펙 2.2절 표를 정식 파이프라인으로 재현

**이 태스크가 실패하면 이후 태스크를 진행하지 않는다.** 스펙의 모든 결론은 임시 SQL(`floor(epoch/180)`)로 뽑은 표 하나에 얹혀 있다. 정식 리샘플러가 같은 표를 내지 못하면 스펙 2.2절부터 다시 봐야 한다.

**Files:**
- Create: `scripts/discovery/intraday_rebound/reproduce.py`

**Interfaces:**
- Consumes: `universe.load_universe`, `resample.resample_ohlcv`, `labeler.compute_labels`, `db.read_sql`
- Produces: `reproduce.reproduce_spec_table(start: str, end: str) -> pd.DataFrame`

**재현 대상 (2026-06-01~2026-06-30, 199종목, TF=3, N=60, M=60, theta=0.03, min_lookback=15분).**

목표값은 **독립 구현(진단 SQL)** 이 낸 값이다. 최초 스펙의 임시 SQL은 워밍업 미제외 + 정규장 필터 부재로 오염돼 있었고, 이 게이트가 그것을 잡아냈다. 아래 표는 그 두 결함을 고친 SQL의 출력이며, 정식 파이프라인과 이미 12/12 일치함이 확인됐다. **두 세그먼트를 분리해서 재현해야 한다.**

`is_full_lookback = True` (10시 이후, 직전 60분 고점):

| 버킷 | n | pct_up | pct_dn | up_over_dn |
|---|---|---|---|---|
| `no_drop` | 276,880 | 4.30 | 3.90 | 1.100 |
| `1.5-2.5%` | 82,882 | 6.61 | 6.52 | 1.014 |
| `2.5-4.0%` | 44,833 | 10.42 | 10.23 | 1.018 |
| `>=4.0%` | 20,286 | 17.76 | 13.18 | 1.348 |

`is_full_lookback = False` (개장 60분, 장 시작 이후 고점, 최소 15분 경과):

| 버킷 | n | pct_up | pct_dn | up_over_dn |
|---|---|---|---|---|
| `no_drop` | 17,214 | 17.20 | 15.88 | 1.083 |
| `1.5-2.5%` | 11,663 | 15.12 | 13.72 | 1.102 |
| `2.5-4.0%` | 13,621 | 17.55 | 14.46 | 1.214 |
| `>=4.0%` | 17,337 | 22.37 | 18.14 | 1.233 |

**허용 오차:** 도달률 절대 **±0.3%p**, 표본 수 상대 **±1%**. 진단 SQL과 파이프라인은 이미 정확히 일치했으므로 여유는 좁다.

**`up_over_dn`은 반드시 반올림 전 원 평균으로 계산한다** (`sum(up)/sum(dn)`). 반올림된 백분율끼리 나누면 `no_drop`이 1.100 대신 1.103이 된다.

- [ ] **Step 1: `reproduce.py` 작성**

```python
# scripts/discovery/intraday_rebound/reproduce.py
"""스펙 2.2절 표를 정식 파이프라인(TimeFrameConverter)으로 재현한다.

임시 SQL(floor(epoch/180))과 결과가 어긋나면 스펙의 결론부터 재검토해야 한다.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from .db import MINUTE_DB, read_sql
from .labeler import LabelParams, compute_labels
from .resample import resample_ohlcv
from .universe import load_universe

_DAYS_SQL = """
SELECT DISTINCT trade_date FROM minute_candles
WHERE trade_date BETWEEN %s AND %s ORDER BY trade_date
"""

_BARS_SQL = """
SELECT stock_code, datetime, open, high, low, close, volume, amount
FROM minute_candles
WHERE trade_date = %s AND stock_code = ANY(%s)
ORDER BY stock_code, datetime
"""

REGULAR_OPEN = pd.Timestamp("09:00:00").time()
REGULAR_CLOSE = pd.Timestamp("15:30:00").time()


def _filter_regular_session(df: pd.DataFrame) -> pd.DataFrame:
    t = df["datetime"].dt.time
    return df[(t >= REGULAR_OPEN) & (t <= REGULAR_CLOSE)]


def _bucket(drop: float) -> str:
    if np.isnan(drop):
        return "na"
    if drop <= -0.04:
        return ">=4.0%"
    if drop <= -0.025:
        return "2.5-4.0%"
    if drop <= -0.015:
        return "1.5-2.5%"
    return "no_drop"


def reproduce_spec_table(start: str = "20260601", end: str = "20260630") -> pd.DataFrame:
    codes = load_universe()
    days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()
    params = LabelParams(timeframe_minutes=3, lookback_min=60, drop_pct=0.0,
                         forward_min=60, theta=0.03, min_lookback_min=15)

    frames = []
    for day in days:
        raw = read_sql(_BARS_SQL, (day, codes), MINUTE_DB)
        if raw.empty:
            continue
        raw["datetime"] = pd.to_datetime(raw["datetime"])
        raw = _filter_regular_session(raw)

        for code, g in raw.groupby("stock_code", sort=False):
            bars = resample_ohlcv(g, params.timeframe_minutes)
            if len(bars) < params.min_lookback_bars + 2:
                continue
            lab = compute_labels(bars, params)
            lab = lab[lab["prior_high"].notna() & (lab["forward_bars"] > 0)]
            frames.append(lab[["drop_pct_actual", "hit_up", "hit_down",
                               "is_full_lookback"]])

    all_lab = pd.concat(frames, ignore_index=True)
    all_lab["bucket"] = all_lab["drop_pct_actual"].map(_bucket)
    all_lab["segment"] = np.where(all_lab["is_full_lookback"], "full", "partial")

    agg = all_lab.groupby(["segment", "bucket"]).agg(
        n=("hit_up", "size"),
        up_mean=("hit_up", "mean"),
        dn_mean=("hit_down", "mean"),
    ).reset_index()

    # 비율은 반올림 전 원 평균으로. 반올림된 백분율끼리 나누면 오차가 생긴다.
    agg["up_over_dn"] = (agg["up_mean"] / agg["dn_mean"]).round(3)
    agg["pct_up"] = (agg["up_mean"] * 100).round(2)
    agg["pct_dn"] = (agg["dn_mean"] * 100).round(2)

    cols = ["segment", "bucket", "n", "pct_up", "pct_dn", "up_over_dn"]
    return agg[cols].sort_values(["segment", "bucket"]).reset_index(drop=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20260601")
    ap.add_argument("--end", default="20260630")
    args = ap.parse_args()
    print(reproduce_spec_table(args.start, args.end).to_string(index=False))
```

`drop_pct=0.0`을 넘겨 모든 봉을 유지하고, 버킷팅은 `drop_pct_actual`로 사후에 한다. 그래야 `no_drop` 베이스라인이 함께 나온다. `is_candidate` 컬럼은 **쓰지 않는다** — `drop_pct=0`이면 신고가 봉(`close > prior_high`)이 빠지는데, 그 봉들도 `no_drop` 베이스라인에 들어가야 한다.

`min_lookback_bars + 2`로 스킵 조건을 완화했다. 예전 `lookback_bars + 2`(=22봉)는 개장 구간 봉을 통째로 버리던 조건의 일부였다.

- [ ] **Step 2: 실행**

Run:
```bash
cd D:/tmp/wt-intraday-rebound/RoboTrader_template
python -m scripts.discovery.intraday_rebound.reproduce --start 20260601 --end 20260630
```

Expected (허용 오차 내, 8행):
```
segment     bucket       n  pct_up  pct_dn  up_over_dn
   full    no_drop  276880    4.30    3.90       1.100
   full  1.5-2.5%   82882    6.61    6.52       1.014
   full  2.5-4.0%   44833   10.42   10.23       1.018
   full    >=4.0%   20286   17.76   13.18       1.348
partial    no_drop   17214   17.20   15.88       1.083
partial  1.5-2.5%   11663   15.12   13.72       1.102
partial  2.5-4.0%   13621   17.55   14.46       1.214
partial    >=4.0%   17337   22.37   18.14       1.233
```
(정렬 순서는 `bucket` 문자열 정렬을 따르므로 위와 다를 수 있다. 값만 대조하라.)

- [ ] **Step 3: 판정**

**통과 조건 넷을 모두 만족해야 한다.**
1. 8개 (segment, bucket) 셀 각각의 `pct_up`, `pct_dn`이 목표 대비 절대 ±0.3%p 이내.
2. 8개 셀 각각의 `n`이 목표 대비 상대 ±1% 이내.
3. `full` 세그먼트에서 `up_over_dn`이 `>=4.0%`에서 최대(≈1.348)이고, `1.5-2.5%`(≈1.014)와 `2.5-4.0%`(≈1.018) **둘 다 `no_drop`(≈1.100)보다 낮다.**
4. `partial` 세그먼트에서 `up_over_dn`이 버킷 깊이에 따라 **단조 증가**한다 (1.083 → 1.102 → 1.214 → 1.233).

조건 3과 4가 스펙의 실제 논지다. 조건 3은 "얕은 하락에는 엣지가 없다", 조건 4는 "개장 60분은 질적으로 다른 국면이다".

**하나라도 실패하면 멈추고 사용자에게 보고한다.** 코드를 고쳐서 숫자를 맞추려 하지 말 것. 보고 시 실제 출력 표와 셀별 오차 산술을 포함한다.

- [ ] **Step 4: 재현 결과를 스펙에 기록**

`docs/superpowers/specs/2026-07-09-intraday-rebound-discovery-design.md` 2.2절 두 표 아래에 다음을 추가한다 (실제 실행일로 채운다).

```markdown
**재현 확인 (YYYY-MM-DD, 정식 파이프라인):** `python -m scripts.discovery.intraday_rebound.reproduce`
8개 (segment, bucket) 셀 전부가 독립 진단 SQL과 허용 오차(도달률 ±0.3%p, 표본 ±1%) 내에서 일치했고,
full 세그먼트의 얕은 하락 두 버킷이 베이스라인보다 낮다는 관계와 partial 세그먼트의 단조 증가가 모두 보존되었다.
```

- [ ] **Step 5: 커밋**

```bash
cd D:/tmp/wt-intraday-rebound
git add RoboTrader_template/scripts/discovery/intraday_rebound/reproduce.py docs/superpowers/specs/2026-07-09-intraday-rebound-discovery-design.md
git commit -m "feat(discovery): 스펙 2.2절 재현 게이트 + 재현 결과 기록"
```

---

### Task 5: 특징 계산 + 시점 절단 테스트

**Files:**
- Create: `scripts/discovery/intraday_rebound/features.py`
- Test: `tests/discovery/intraday_rebound/test_features.py`

**Interfaces:**
- Consumes: `resample.resample_ohlcv` 출력, 일간 컨텍스트 dict, 시장 프록시 Series
- Produces:
  ```python
  features.FEATURE_NAMES: list[str]
  features.compute_features(
      bars: pd.DataFrame,
      prior_high: pd.Series,
      daily_ctx: dict,
      market_ret: pd.Series,
      lookback_bars: int,
  ) -> pd.DataFrame   # 길이 == len(bars), 컬럼 == FEATURE_NAMES
  ```
  - `daily_ctx` 키: `gap_pct, ret_5d, ret_20d, dev_ma20, atr14_pct, market_cap, amount_rank`
    (전부 T−1 확정 일봉에서 유도된 **스칼라**. 당일 정보가 섞이면 누수다. 단 `gap_pct`는 당일 시가를 쓰므로 예외이며, 시가는 `t>=1`에서 이미 관측된 값이다.)
  - `market_ret[t]`: 동시각 유니버스 수익률 중앙값 (Task 8에서 사전 계산해 주입)
  - `prior_high`: `labeler.compute_labels` 출력의 동명 컬럼

**FEATURE_NAMES (18개)**

```python
FEATURE_NAMES = [
    # A. 하락 구조
    "drop_pct", "drop_over_atr", "drop_speed", "consec_down", "range_expansion",
    # B. 저점 캔들 형상
    "lower_wick_ratio", "body_ratio", "close_pos_in_day",
    # C. 거래량
    "vol_z", "vol_ratio_drop", "log_amount_cum",
    # D. 시간
    "minutes_since_open",
    # E. 일간 컨텍스트
    "gap_pct", "ret_5d", "ret_20d", "dev_ma20",
    # F. 시장·횡단면
    "market_ret", "rel_drop",
]
```

`atr14_pct`, `market_cap`, `amount_rank`는 특징이 아니라 **층화 변수**로 따로 나간다(랭킹에서 사용). `breadth`는 Task 8에서 `market_ret`와 함께 계산되나 이번 라운드 특징 목록에서는 제외한다 — `market_ret`과 상관이 매우 높아 단변량 랭킹에 중복 정보를 넣는다. (스펙 6절 F의 breadth는 다음 라운드로 이월.)

**시간대 버킷**은 `minutes_since_open`으로 대체한다. 단변량 AUC는 연속 변수에 대해 정의되며, 버킷은 정보를 버린다. 리포트에서 5분위로 나눠 보여준다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/discovery/intraday_rebound/test_features.py
import numpy as np
import pandas as pd
import pytest

from scripts.discovery.intraday_rebound.features import FEATURE_NAMES, compute_features


DAILY_CTX = {
    "gap_pct": -0.01, "ret_5d": -0.05, "ret_20d": 0.02,
    "dev_ma20": -0.08, "atr14_pct": 0.03,
    "market_cap": 1e12, "amount_rank": 0.7,
}


def _bars(n=20, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    open_ = close + rng.normal(0, 0.3, n)
    return pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=n, freq="3min"),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": rng.integers(1, 100, n).astype(float),
        "amount": rng.integers(100, 10000, n).astype(float),
        "bar_count": [3] * n,
    })


def _ctx(bars):
    prior_high = bars["high"].rolling(20, min_periods=20).max().shift(1)
    market_ret = pd.Series(np.linspace(-0.01, 0.01, len(bars)))
    return prior_high, market_ret


def test_returns_all_feature_columns_with_matching_length():
    bars = _bars()
    prior_high, market_ret = _ctx(bars)
    out = compute_features(bars, prior_high, DAILY_CTX, market_ret, lookback_bars=20)
    assert list(out.columns) == FEATURE_NAMES
    assert len(out) == len(bars)


def test_time_truncation_no_lookahead():
    """t 이후 데이터를 NaN으로 지워도 t행의 특징이 바뀌면 안 된다."""
    bars = _bars(n=30)
    prior_high, market_ret = _ctx(bars)
    full = compute_features(bars, prior_high, DAILY_CTX, market_ret, lookback_bars=20)

    for t in (10, 20, 29):
        truncated = bars.copy()
        cols = ["open", "high", "low", "close", "volume", "amount"]
        truncated.loc[t + 1:, cols] = np.nan
        ph_trunc = prior_high.copy()
        ph_trunc.loc[t + 1:] = np.nan
        mr_trunc = market_ret.copy()
        mr_trunc.loc[t + 1:] = np.nan

        partial = compute_features(truncated, ph_trunc, DAILY_CTX, mr_trunc,
                                   lookback_bars=20)
        pd.testing.assert_series_equal(
            full.iloc[t], partial.iloc[t], check_names=False,
            obj=f"row {t} changed when future was erased",
        )


def test_rel_drop_is_drop_minus_market_return():
    bars = _bars()
    prior_high, market_ret = _ctx(bars)
    out = compute_features(bars, prior_high, DAILY_CTX, market_ret, lookback_bars=20)
    np.testing.assert_allclose(
        out["rel_drop"].to_numpy(),
        (out["drop_pct"] - out["market_ret"]).to_numpy(),
        equal_nan=True,
    )


def test_lower_wick_ratio_bounds():
    bars = pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=1, freq="3min"),
        "open": [100.0], "high": [110.0], "low": [90.0], "close": [95.0],
        "volume": [1.0], "amount": [1.0], "bar_count": [3],
    })
    prior_high = pd.Series([np.nan])
    market_ret = pd.Series([0.0])
    out = compute_features(bars, prior_high, DAILY_CTX, market_ret, lookback_bars=1)
    # (close - low) / (high - low) = (95-90)/(110-90) = 0.25
    assert out.loc[0, "lower_wick_ratio"] == pytest.approx(0.25)


def test_zero_range_bar_does_not_divide_by_zero():
    bars = pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=1, freq="3min"),
        "open": [100.0], "high": [100.0], "low": [100.0], "close": [100.0],
        "volume": [1.0], "amount": [1.0], "bar_count": [3],
    })
    out = compute_features(bars, pd.Series([np.nan]), DAILY_CTX,
                           pd.Series([0.0]), lookback_bars=1)
    assert np.isnan(out.loc[0, "lower_wick_ratio"])
    assert np.isnan(out.loc[0, "body_ratio"])


def test_consec_down_counts_consecutive_bearish_bars():
    bars = pd.DataFrame({
        "datetime": pd.date_range("2026-06-01 09:00", periods=4, freq="3min"),
        "open": [100.0, 100.0, 100.0, 100.0],
        "high": [101.0, 101.0, 101.0, 101.0],
        "low": [98.0, 98.0, 98.0, 98.0],
        "close": [99.0, 98.0, 99.5, 98.0],   # down, down, up, down
        "volume": [1.0] * 4, "amount": [1.0] * 4, "bar_count": [3] * 4,
    })
    out = compute_features(bars, pd.Series([np.nan] * 4), DAILY_CTX,
                           pd.Series([0.0] * 4), lookback_bars=1)
    assert out["consec_down"].tolist() == [1.0, 2.0, 0.0, 1.0]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd D:/tmp/wt-intraday-rebound/RoboTrader_template && python -m pytest tests/discovery/intraday_rebound/test_features.py -v`
Expected: FAIL — `ModuleNotFoundError: ... features`

- [ ] **Step 3: `features.py` 구현**

```python
# scripts/discovery/intraday_rebound/features.py
"""반등 직전 시점의 특징. 시점 t까지의 정보만 사용한다.

모든 rolling/expanding 은 과거 방향이다. shift(-k) 를 쓰면 누수다.
test_time_truncation_no_lookahead 가 이를 기계적으로 강제한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_NAMES = [
    "drop_pct", "drop_over_atr", "drop_speed", "consec_down", "range_expansion",
    "lower_wick_ratio", "body_ratio", "close_pos_in_day",
    "vol_z", "vol_ratio_drop", "log_amount_cum",
    "minutes_since_open",
    "gap_pct", "ret_5d", "ret_20d", "dev_ma20",
    "market_ret", "rel_drop",
]

_EPS = 1e-12


def _safe_div(a, b):
    b = np.where(np.abs(b) < _EPS, np.nan, b)
    return a / b


def _bars_since_prior_high(high: pd.Series, lookback_bars: int) -> pd.Series:
    """직전 lookback_bars 봉 중 최고가가 몇 봉 전이었는지 (자기 봉 제외)."""
    def _idx(window: np.ndarray) -> float:
        return float(len(window) - int(np.argmax(window)))

    return high.shift(1).rolling(lookback_bars, min_periods=1).apply(_idx, raw=True)


def _consec_down(close: pd.Series, open_: pd.Series) -> pd.Series:
    bearish = (close < open_).to_numpy()
    out = np.zeros(len(bearish))
    run = 0
    for i, b in enumerate(bearish):
        run = run + 1 if b else 0
        out[i] = run
    return pd.Series(out, index=close.index)


def compute_features(bars: pd.DataFrame,
                     prior_high: pd.Series,
                     daily_ctx: dict,
                     market_ret: pd.Series,
                     lookback_bars: int) -> pd.DataFrame:
    b = bars.reset_index(drop=True)
    prior_high = pd.Series(prior_high).reset_index(drop=True)
    market_ret = pd.Series(market_ret).reset_index(drop=True)

    o, h, l, c = b["open"], b["high"], b["low"], b["close"]
    vol, amt = b["volume"], b["amount"]

    rng = (h - l).to_numpy(dtype=float)

    drop_pct = pd.Series(_safe_div(c.to_numpy(dtype=float),
                                   prior_high.to_numpy(dtype=float)) - 1.0)
    atr = float(daily_ctx["atr14_pct"])
    drop_over_atr = drop_pct / atr if abs(atr) > _EPS else pd.Series(np.nan, index=b.index)

    bars_since = _bars_since_prior_high(h, lookback_bars)
    drop_speed = pd.Series(_safe_div(drop_pct.to_numpy(dtype=float),
                                     bars_since.to_numpy(dtype=float)))

    consec_down = _consec_down(c, o)

    avg_range_so_far = pd.Series(rng).expanding(min_periods=1).mean()
    recent_range = pd.Series(rng).rolling(3, min_periods=1).mean()
    range_expansion = pd.Series(_safe_div(recent_range.to_numpy(),
                                          avg_range_so_far.to_numpy()))

    lower_wick_ratio = pd.Series(_safe_div((c - l).to_numpy(dtype=float), rng))
    body_ratio = pd.Series(_safe_div((c - o).abs().to_numpy(dtype=float), rng))

    day_high = h.expanding(min_periods=1).max()
    day_low = l.expanding(min_periods=1).min()
    close_pos_in_day = pd.Series(_safe_div(
        (c - day_low).to_numpy(dtype=float),
        (day_high - day_low).to_numpy(dtype=float),
    ))

    vol_mean = vol.expanding(min_periods=1).mean()
    vol_std = vol.expanding(min_periods=2).std()
    vol_z = pd.Series(_safe_div((vol - vol_mean).to_numpy(dtype=float),
                                vol_std.to_numpy(dtype=float)))

    vol_recent = vol.rolling(3, min_periods=1).mean()
    vol_ratio_drop = pd.Series(_safe_div(vol_recent.to_numpy(), vol_mean.to_numpy()))

    log_amount_cum = np.log1p(amt.cumsum())

    session_open = b["datetime"].iloc[0].normalize() + pd.Timedelta(hours=9)
    minutes_since_open = (b["datetime"] - session_open).dt.total_seconds() / 60.0

    n = len(b)
    out = pd.DataFrame({
        "drop_pct": drop_pct,
        "drop_over_atr": drop_over_atr,
        "drop_speed": drop_speed,
        "consec_down": consec_down,
        "range_expansion": range_expansion,
        "lower_wick_ratio": lower_wick_ratio,
        "body_ratio": body_ratio,
        "close_pos_in_day": close_pos_in_day,
        "vol_z": vol_z,
        "vol_ratio_drop": vol_ratio_drop,
        "log_amount_cum": log_amount_cum,
        "minutes_since_open": minutes_since_open,
        "gap_pct": np.full(n, daily_ctx["gap_pct"]),
        "ret_5d": np.full(n, daily_ctx["ret_5d"]),
        "ret_20d": np.full(n, daily_ctx["ret_20d"]),
        "dev_ma20": np.full(n, daily_ctx["dev_ma20"]),
        "market_ret": market_ret,
    })
    out["rel_drop"] = out["drop_pct"] - out["market_ret"]
    return out[FEATURE_NAMES]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd D:/tmp/wt-intraday-rebound/RoboTrader_template && python -m pytest tests/discovery/intraday_rebound/test_features.py -v`
Expected: 6 passed

`test_time_truncation_no_lookahead`가 실패하면 **어떤 특징이 미래를 보고 있다.** 실패한 컬럼명이 정확한 범인이다. `expanding()`/`rolling()`은 안전하고, `.mean()` 같은 전역 집계나 `shift(-k)`는 위험하다.

- [ ] **Step 5: 커밋**

```bash
cd D:/tmp/wt-intraday-rebound
git add RoboTrader_template/scripts/discovery/intraday_rebound/features.py RoboTrader_template/tests/discovery/intraday_rebound/test_features.py
git commit -m "feat(discovery): 특징 18종 + 시점절단 누수 테스트"
```

---

### Task 6: 랭킹 (층화 AUC, 방향성 AUC, 날짜 블록 부트스트랩)

**Files:**
- Create: `scripts/discovery/intraday_rebound/ranking.py`
- Test: `tests/discovery/intraday_rebound/test_ranking.py`

**Interfaces:**
- Consumes: 라벨+특징 DataFrame
- Produces:
  ```python
  ranking.stratified_auc(score: np.ndarray, label: np.ndarray, strata: np.ndarray) -> float
  ranking.directional_auc(score, hit_up, hit_down, strata) -> float
  ranking.date_block_bootstrap_ci(fn, dates, n_boot=1000, seed=42, alpha=0.05) -> tuple[float, float]
  ranking.rank_features(df: pd.DataFrame, feature_names: list[str],
                        strata_col: str = "atr_quintile",
                        date_col: str = "trade_date") -> pd.DataFrame
  ```
  `rank_features` 출력 컬럼: `feature, auc_up, auc_down, directional_auc, ci_lo, ci_hi, n_dates`

**핵심 정의**

- `stratified_auc`: 층(strata) 안에서 AUC를 계산하고 층 크기로 가중평균. 한 층에 양성 또는 음성이 하나도 없으면 그 층은 건너뛴다.
- `directional_auc = stratified_auc(score, hit_up) − stratified_auc(score, hit_down)`. 0에 가까우면 그 특징은 변동성을 재고 있을 뿐이다.
- 부트스트랩 블록은 **날짜**다. 봉이 아니다 (스펙 2.3절).
- **층은 `atr_quintile × is_full_lookback` 이원이다** (스펙 5·7절). `rank_features`는 두 컬럼을 결합한 복합 층을 만든다:
  ```python
  strata = df[strata_col].astype(str) + "|" + df["is_full_lookback"].astype(str)
  ```
  ATR만으로 층화하면 개장 60분의 짧은 룩백이 변동성으로 위장해 들어온다. 스펙 2.2절이 보여주듯 두 세그먼트는 얕은 하락 버킷에서 부호가 반대다 — 합치면 서로를 지운다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/discovery/intraday_rebound/test_ranking.py
import numpy as np
import pandas as pd
import pytest

from scripts.discovery.intraday_rebound.ranking import (
    date_block_bootstrap_ci,
    directional_auc,
    rank_features,
    stratified_auc,
)


def test_stratified_auc_perfect_separation_is_one():
    score = np.array([1.0, 2.0, 3.0, 4.0])
    label = np.array([0, 0, 1, 1])
    strata = np.zeros(4)
    assert stratified_auc(score, label, strata) == pytest.approx(1.0)


def test_stratified_auc_ignores_strata_without_both_classes():
    score = np.array([1.0, 2.0, 3.0, 4.0, 9.0, 9.5])
    label = np.array([0, 0, 1, 1, 1, 1])       # stratum 1 has only positives
    strata = np.array([0, 0, 0, 0, 1, 1])
    assert stratified_auc(score, label, strata) == pytest.approx(1.0)


def test_stratified_auc_cancels_a_pure_volatility_proxy():
    """층 안에서는 무작위, 층 간에만 분리되는 점수는 층화 AUC가 0.5로 붕괴한다."""
    rng = np.random.default_rng(0)
    n = 2000
    strata = rng.integers(0, 2, n)
    # 점수는 층을 그대로 반영, 라벨도 층에 따라 확률이 다름
    score = strata + rng.normal(0, 0.01, n)
    label = (rng.random(n) < np.where(strata == 1, 0.4, 0.1)).astype(int)

    naive = stratified_auc(score, label, np.zeros(n))
    strat = stratified_auc(score, label, strata)
    assert naive > 0.65          # 층화하지 않으면 잘 맞히는 것처럼 보인다
    assert abs(strat - 0.5) < 0.05  # 층화하면 힘을 잃는다


def test_directional_auc_is_zero_for_symmetric_volatility_signal():
    rng = np.random.default_rng(1)
    n = 4000
    score = rng.normal(0, 1, n)
    p = 1 / (1 + np.exp(-score))         # 점수가 크면 위아래로 다 잘 간다
    hit_up = (rng.random(n) < p).astype(int)
    hit_down = (rng.random(n) < p).astype(int)
    strata = np.zeros(n)
    d = directional_auc(score, hit_up, hit_down, strata)
    assert abs(d) < 0.03


def test_directional_auc_positive_for_true_up_only_signal():
    rng = np.random.default_rng(2)
    n = 4000
    score = rng.normal(0, 1, n)
    p_up = 1 / (1 + np.exp(-score))
    hit_up = (rng.random(n) < p_up).astype(int)
    hit_down = (rng.random(n) < 0.3).astype(int)   # 점수와 무관
    d = directional_auc(score, hit_up, hit_down, np.zeros(n))
    assert d > 0.15


def test_date_block_bootstrap_ci_brackets_the_point_estimate():
    rng = np.random.default_rng(3)
    dates = np.repeat(np.arange(50), 20)

    def fn(idx):
        return float(np.mean(idx % 7 == 0))

    lo, hi = date_block_bootstrap_ci(fn, dates, n_boot=200, seed=7)
    point = fn(np.arange(len(dates)))
    assert lo <= point <= hi


def test_rank_features_shuffled_labels_collapse_to_zero():
    """셔플 테스트: 라벨을 날짜 블록 안에서 섞으면 방향성 AUC가 0으로 무너진다."""
    rng = np.random.default_rng(4)
    n = 3000
    dates = rng.integers(0, 60, n)
    df = pd.DataFrame({
        "trade_date": dates,
        "atr_quintile": rng.integers(0, 5, n),
        "feat_a": rng.normal(0, 1, n),
    })
    df["hit_up"] = rng.integers(0, 2, n)
    df["hit_down"] = rng.integers(0, 2, n)

    out = rank_features(df, ["feat_a"])
    assert abs(float(out.loc[0, "directional_auc"])) < 0.06
    assert out.loc[0, "ci_lo"] < 0 < out.loc[0, "ci_hi"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd D:/tmp/wt-intraday-rebound/RoboTrader_template && python -m pytest tests/discovery/intraday_rebound/test_ranking.py -v`
Expected: FAIL — `ModuleNotFoundError: ... ranking`

- [ ] **Step 3: `ranking.py` 구현**

```python
# scripts/discovery/intraday_rebound/ranking.py
"""특징 랭킹. 변동성 프록시를 죽이는 세 겹 방어:
1) 층화 AUC (ATR 5분위 안에서 비교)
2) 방향성 AUC = AUC(hit_up) - AUC(hit_down)
3) 날짜 블록 부트스트랩 (유효 표본은 봉이 아니라 날짜)
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score


def stratified_auc(score: np.ndarray, label: np.ndarray, strata: np.ndarray) -> float:
    score = np.asarray(score, dtype=float)
    label = np.asarray(label, dtype=float)
    strata = np.asarray(strata)

    ok = np.isfinite(score) & np.isfinite(label)
    score, label, strata = score[ok], label[ok], strata[ok]
    if len(score) == 0:
        return float("nan")

    total_w, acc = 0.0, 0.0
    for s in np.unique(strata):
        m = strata == s
        y = label[m]
        if y.min() == y.max():      # 한 클래스만 있는 층은 건너뛴다
            continue
        w = float(m.sum())
        acc += w * roc_auc_score(y, score[m])
        total_w += w

    return acc / total_w if total_w > 0 else float("nan")


def directional_auc(score, hit_up, hit_down, strata) -> float:
    up = stratified_auc(score, hit_up, strata)
    dn = stratified_auc(score, hit_down, strata)
    if np.isnan(up) or np.isnan(dn):
        return float("nan")
    return up - dn


def date_block_bootstrap_ci(fn: Callable[[np.ndarray], float],
                            dates: np.ndarray,
                            n_boot: int = 1000,
                            seed: int = 42,
                            alpha: float = 0.05) -> tuple[float, float]:
    """날짜를 복원추출해 fn 의 신뢰구간을 낸다. fn 은 행 인덱스 배열을 받는다."""
    dates = np.asarray(dates)
    uniq = np.unique(dates)
    idx_by_date = {d: np.flatnonzero(dates == d) for d in uniq}

    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(n_boot):
        picked = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by_date[d] for d in picked])
        v = fn(idx)
        if np.isfinite(v):
            stats.append(v)

    if not stats:
        return (float("nan"), float("nan"))
    lo = float(np.quantile(stats, alpha / 2))
    hi = float(np.quantile(stats, 1 - alpha / 2))
    return lo, hi


def rank_features(df: pd.DataFrame,
                  feature_names: list[str],
                  strata_col: str = "atr_quintile",
                  date_col: str = "trade_date",
                  n_boot: int = 500,
                  seed: int = 42) -> pd.DataFrame:
    dates = df[date_col].to_numpy()
    strata = df[strata_col].to_numpy()
    up = df["hit_up"].to_numpy(dtype=float)
    dn = df["hit_down"].to_numpy(dtype=float)

    rows = []
    for feat in feature_names:
        score = df[feat].to_numpy(dtype=float)

        auc_up = stratified_auc(score, up, strata)
        auc_dn = stratified_auc(score, dn, strata)
        d = auc_up - auc_dn if np.isfinite(auc_up) and np.isfinite(auc_dn) else np.nan

        def _fn(idx, _s=score):
            return directional_auc(_s[idx], up[idx], dn[idx], strata[idx])

        lo, hi = date_block_bootstrap_ci(_fn, dates, n_boot=n_boot, seed=seed)

        rows.append({
            "feature": feat, "auc_up": auc_up, "auc_down": auc_dn,
            "directional_auc": d, "ci_lo": lo, "ci_hi": hi,
            "n_dates": len(np.unique(dates)),
        })

    out = pd.DataFrame(rows)
    return out.reindex(out["directional_auc"].abs().sort_values(ascending=False).index).reset_index(drop=True)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd D:/tmp/wt-intraday-rebound/RoboTrader_template && python -m pytest tests/discovery/intraday_rebound/test_ranking.py -v`
Expected: 7 passed

`test_stratified_auc_cancels_a_pure_volatility_proxy`와 `test_directional_auc_is_zero_for_symmetric_volatility_signal`이 이 라운드의 방법론적 심장이다. 이 둘이 통과하면 스펙 2.2절의 실수는 구조적으로 재발할 수 없다.

- [ ] **Step 5: 커밋**

```bash
cd D:/tmp/wt-intraday-rebound
git add RoboTrader_template/scripts/discovery/intraday_rebound/ranking.py RoboTrader_template/tests/discovery/intraday_rebound/test_ranking.py
git commit -m "feat(discovery): 층화 AUC + 방향성 AUC + 날짜 블록 부트스트랩"
```

---

### Task 7: 모양 프로브 (KMeans)

**Files:**
- Create: `scripts/discovery/intraday_rebound/shape_probe.py`
- Test: `tests/discovery/intraday_rebound/test_shape_probe.py`
- Modify: `docs/superpowers/specs/2026-07-09-intraday-rebound-discovery-design.md` (8절 k-Shape → KMeans)

**Interfaces:**
- Consumes: 이벤트 테이블 (종목-일당 첫 딥드롭 봉 1개)
- Produces:
  ```python
  shape_probe.znorm_windows(seq: np.ndarray) -> np.ndarray   # (n, w) → (n, w)
  shape_probe.cluster_shapes(windows: np.ndarray, k: int, seed: int = 42) -> np.ndarray
  shape_probe.probe_report(events: pd.DataFrame, windows: np.ndarray, k: int) -> pd.DataFrame
  ```
  `probe_report` 출력 컬럼: `cluster, n, pct_up, pct_down, up_over_down, mean_atr_pct, ci_lo, ci_hi`

**이벤트 정의 (스펙 8절):** 종목-일당 **첫 번째** 딥드롭 봉 하나. 겹친 봉을 다 넣으면 같은 하락 하나가 클러스터를 지배한다.

**필수:** `mean_atr_pct`를 반드시 함께 낸다. 없으면 "모양 3번이 잘 반등한다"가 "모양 3번은 변동성 큰 종목에서 나온다"일 수 있다.

- [ ] **Step 1: 스펙 8절 수정**

`docs/superpowers/specs/2026-07-09-intraday-rebound-discovery-design.md`의 8절에서 다음 문장을

> **방법:** 각 이벤트의 직전 20봉 종가를 z-정규화한 20차원 벡터를 만들고, k-Shape로 8~12개 클러스터로 나눈다.

다음으로 교체한다.

```markdown
**방법:** 각 이벤트의 직전 20봉 종가를 z-정규화한 20차원 벡터를 만들고,
`sklearn.cluster.KMeans`(유클리드)로 8~12개 클러스터로 나눈다.

**k-Shape 대신 KMeans인 이유.** k-Shape의 핵심은 시프트 불변 거리다. 그러나 우리 시퀀스는
딥 드롭 봉에 앵커링되어 있어(20봉이 임의 위치가 아니라 "이벤트 직전"으로 정렬돼 있다)
시프트 불변성은 오히려 그 정렬 정보를 버린다. 또한 `tslearn`은 미설치이며 새 의존성을
추가하지 않는다. z-정규화된 벡터 위의 유클리드 거리는 상관계수의 단조 변환이므로
"모양이 비슷한가"를 그대로 잰다.
```

8절 제목도 `## 8. 모양 프로브 (KMeans)`로 바꾼다.

- [ ] **Step 2: 실패하는 테스트 작성**

```python
# tests/discovery/intraday_rebound/test_shape_probe.py
import numpy as np
import pandas as pd
import pytest

from scripts.discovery.intraday_rebound.shape_probe import (
    cluster_shapes,
    probe_report,
    znorm_windows,
)


def test_znorm_gives_zero_mean_unit_std_per_row():
    w = np.array([[1.0, 2.0, 3.0], [10.0, 20.0, 30.0]])
    z = znorm_windows(w)
    np.testing.assert_allclose(z.mean(axis=1), [0.0, 0.0], atol=1e-9)
    np.testing.assert_allclose(z.std(axis=1), [1.0, 1.0], atol=1e-9)


def test_znorm_makes_scaled_shapes_identical():
    """모양이 같고 크기만 다른 두 시퀀스는 정규화 후 같아진다."""
    a = np.array([[1.0, 2.0, 3.0, 2.0]])
    b = a * 100.0
    np.testing.assert_allclose(znorm_windows(a), znorm_windows(b), atol=1e-9)


def test_znorm_flat_window_returns_zeros_not_nan():
    z = znorm_windows(np.array([[5.0, 5.0, 5.0]]))
    assert np.all(z == 0.0)


def test_cluster_shapes_recovers_two_planted_shapes():
    rng = np.random.default_rng(0)
    up = np.tile(np.linspace(0, 1, 20), (100, 1)) + rng.normal(0, 0.01, (100, 20))
    dn = np.tile(np.linspace(1, 0, 20), (100, 1)) + rng.normal(0, 0.01, (100, 20))
    w = znorm_windows(np.vstack([up, dn]))

    labels = cluster_shapes(w, k=2, seed=0)
    # 각 심은 모양이 한 클러스터에 몰려야 한다
    assert len(np.unique(labels[:100])) == 1
    assert len(np.unique(labels[100:])) == 1
    assert labels[0] != labels[100]


def test_probe_report_has_atr_column_and_one_row_per_cluster():
    rng = np.random.default_rng(1)
    n = 200
    events = pd.DataFrame({
        "trade_date": rng.integers(0, 20, n),
        "hit_up": rng.integers(0, 2, n),
        "hit_down": rng.integers(0, 2, n),
        "atr14_pct": rng.uniform(0.01, 0.05, n),
    })
    windows = znorm_windows(rng.normal(0, 1, (n, 20)))

    rep = probe_report(events, windows, k=4)
    assert len(rep) == 4
    assert "mean_atr_pct" in rep.columns
    assert set(["cluster", "n", "pct_up", "pct_down", "up_over_down",
                "ci_lo", "ci_hi"]).issubset(rep.columns)
    assert rep["n"].sum() == n


def test_probe_report_is_deterministic_for_fixed_seed():
    rng = np.random.default_rng(2)
    n = 150
    events = pd.DataFrame({
        "trade_date": rng.integers(0, 15, n),
        "hit_up": rng.integers(0, 2, n),
        "hit_down": rng.integers(0, 2, n),
        "atr14_pct": rng.uniform(0.01, 0.05, n),
    })
    windows = znorm_windows(rng.normal(0, 1, (n, 20)))
    a = probe_report(events, windows, k=3)
    b = probe_report(events, windows, k=3)
    pd.testing.assert_frame_equal(a, b)
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd D:/tmp/wt-intraday-rebound/RoboTrader_template && python -m pytest tests/discovery/intraday_rebound/test_shape_probe.py -v`
Expected: FAIL — `ModuleNotFoundError: ... shape_probe`

- [ ] **Step 4: `shape_probe.py` 구현**

```python
# scripts/discovery/intraday_rebound/shape_probe.py
"""모양 프로브: 캔들 모양에 손 특징이 못 잡은 정보가 있는가?

판정만 한다. 진입 룰은 만들지 않는다.
클러스터별 평균 ATR을 반드시 병기한다 — 없으면 "모양"이 "변동성"의 가면일 수 있다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from .ranking import date_block_bootstrap_ci

_EPS = 1e-12


def znorm_windows(seq: np.ndarray) -> np.ndarray:
    """행 단위 z-정규화. 평탄한 행은 0 벡터로 (NaN 금지)."""
    x = np.asarray(seq, dtype=float)
    mu = x.mean(axis=1, keepdims=True)
    sd = x.std(axis=1, keepdims=True)
    flat = sd < _EPS
    sd = np.where(flat, 1.0, sd)
    z = (x - mu) / sd
    z[flat[:, 0]] = 0.0
    return z


def cluster_shapes(windows: np.ndarray, k: int, seed: int = 42) -> np.ndarray:
    km = KMeans(n_clusters=k, n_init=10, random_state=seed)
    return km.fit_predict(np.asarray(windows, dtype=float))


def probe_report(events: pd.DataFrame, windows: np.ndarray, k: int,
                 seed: int = 42, n_boot: int = 300) -> pd.DataFrame:
    labels = cluster_shapes(windows, k=k, seed=seed)
    ev = events.reset_index(drop=True).copy()
    ev["cluster"] = labels

    rows = []
    for cl, g in ev.groupby("cluster", sort=True):
        up = g["hit_up"].to_numpy(dtype=float)
        dn = g["hit_down"].to_numpy(dtype=float)
        dates = g["trade_date"].to_numpy()

        def _ratio(idx, _up=up, _dn=dn):
            d = _dn[idx].mean()
            return _up[idx].mean() / d if d > _EPS else np.nan

        lo, hi = date_block_bootstrap_ci(_ratio, dates, n_boot=n_boot, seed=seed)

        pct_up = float(up.mean())
        pct_dn = float(dn.mean())
        rows.append({
            "cluster": int(cl),
            "n": int(len(g)),
            "pct_up": round(pct_up * 100, 2),
            "pct_down": round(pct_dn * 100, 2),
            "up_over_down": round(pct_up / pct_dn, 3) if pct_dn > _EPS else np.nan,
            "mean_atr_pct": round(float(g["atr14_pct"].mean()), 5),
            "ci_lo": round(lo, 3),
            "ci_hi": round(hi, 3),
        })

    return pd.DataFrame(rows).sort_values("cluster").reset_index(drop=True)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd D:/tmp/wt-intraday-rebound/RoboTrader_template && python -m pytest tests/discovery/intraday_rebound/test_shape_probe.py -v`
Expected: 6 passed

- [ ] **Step 6: 커밋**

```bash
cd D:/tmp/wt-intraday-rebound
git add RoboTrader_template/scripts/discovery/intraday_rebound/shape_probe.py RoboTrader_template/tests/discovery/intraday_rebound/test_shape_probe.py docs/superpowers/specs/2026-07-09-intraday-rebound-discovery-design.md
git commit -m "feat(discovery): 모양 프로브 (KMeans) + 스펙 8절 k-Shape→KMeans 수정"
```

---

### Task 8: 데이터셋 빌드 + 리포트

**Files:**
- Create: `scripts/discovery/intraday_rebound/build_dataset.py`
- Create: `scripts/discovery/intraday_rebound/report.py`

**Interfaces:**
- Consumes: Task 1~7 전부
- Produces:
  - `_cache/labels_tf{TF}_N{N}_D{D}_M{M}.parquet` — 후보 봉만, 특징 + 라벨 + `trade_date, stock_code, atr14_pct, atr_quintile, is_full_lookback, lookback_bars_used`
  - `_cache/events_shape.parquet` — 종목-일당 첫 딥드롭 봉 + 직전 20봉 종가 시퀀스
  - `docs/superpowers/reports/2026-07-09-intraday-rebound-findings.md`

**세그먼트 규칙 (스펙 5·7절).** `is_full_lookback`과 `lookback_bars_used`를 parquet에 반드시 실어야 한다. `grid_table()`은 `["segment", ...]`로 그룹핑해 **두 세그먼트를 분리한 행**만 낸다 — 합산 행을 만들지 않는다. `is_oos_ranking()`은 `rank_features`에 복합 층을 넘긴다. 비율은 반올림 전 원 평균으로 계산한다.

**격자 (스펙 5절):** `TF ∈ {3,5,15}`, `N ∈ {30,60,120}`, `D ∈ {0.025,0.04,0.06,0.08}`, `M ∈ {30,60,120}`, `theta ∈ {0.03}` ∪ `{k×ATR : k ∈ {1,1.5,2}}`.
= 3×3×4×3×4 = **432 격자점**. 봉 계산은 격자점마다 다시 하지 않는다: TF별로 봉을 한 번 만들고, `(N, D, M, theta)`는 그 위에서 재계산한다.

- [ ] **Step 1: `build_dataset.py` 작성**

```python
# scripts/discovery/intraday_rebound/build_dataset.py
"""종목-일 스트리밍 → 리샘플 → 라벨 → 특징 → parquet.

메모리에 전체를 올리지 않는다. 하루치씩 처리하고 격자점별로 append 한다.
"""
from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

from .db import DAILY_DB, MINUTE_DB, read_sql
from .features import FEATURE_NAMES, compute_features
from .labeler import LabelParams, compute_labels
from .resample import resample_ohlcv
from .universe import load_universe

CACHE = Path(__file__).parent / "_cache"

TIMEFRAMES = [3, 5, 15]
LOOKBACKS = [30, 60, 120]
DROPS = [0.025, 0.04, 0.06, 0.08]
FORWARDS = [30, 60, 120]
ATR_MULTIPLES = [None, 1.0, 1.5, 2.0]      # None = 고정 3%
FIXED_THETA = 0.03

REGULAR_OPEN = pd.Timestamp("09:00:00").time()
REGULAR_CLOSE = pd.Timestamp("15:30:00").time()

_DAYS_SQL = """
SELECT DISTINCT trade_date FROM minute_candles
WHERE trade_date BETWEEN %s AND %s ORDER BY trade_date
"""
_BARS_SQL = """
SELECT stock_code, datetime, open, high, low, close, volume, amount
FROM minute_candles WHERE trade_date = %s AND stock_code = ANY(%s)
ORDER BY stock_code, datetime
"""
# daily_prices.date 는 'YYYY-MM-DD' 문자열이다 (minute_candles.trade_date 는 'YYYYMMDD').
_DAILY_SQL = """
SELECT stock_code, date, open, high, low, close, volume, market_cap
FROM daily_prices
WHERE stock_code = ANY(%s) AND date < %s
ORDER BY stock_code, date
"""


def _to_dash(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"


def _daily_context(daily: pd.DataFrame, code: str, day_open: float) -> dict | None:
    g = daily[daily["stock_code"] == code].tail(21)
    if len(g) < 21:
        return None
    c = g["close"].to_numpy(dtype=float)
    h = g["high"].to_numpy(dtype=float)
    l = g["low"].to_numpy(dtype=float)

    prev_close = c[-1]
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]),
                                              np.abs(l[1:] - c[:-1])))
    atr14 = float(np.mean(tr[-14:]))
    ma20 = float(np.mean(c[-20:]))

    return {
        "gap_pct": day_open / prev_close - 1.0,
        "ret_5d": prev_close / c[-6] - 1.0,
        "ret_20d": prev_close / c[-21] - 1.0,
        "dev_ma20": prev_close / ma20 - 1.0,
        "atr14_pct": atr14 / prev_close if prev_close else np.nan,
        "market_cap": float(g["market_cap"].iloc[-1] or 0.0),
        "amount_rank": np.nan,   # Task 8 Step 2 에서 일자별 랭크로 채움
    }


def _market_ret(bars_by_code: dict[str, pd.DataFrame]) -> pd.Series:
    """동시각 유니버스 수익률 중앙값 (시장 프록시)."""
    rets = {}
    for code, b in bars_by_code.items():
        s = b.set_index("datetime")["close"]
        rets[code] = s / s.iloc[0] - 1.0
    return pd.DataFrame(rets).median(axis=1)


def build_day(day: str, codes: list[str], tf: int) -> tuple[dict, pd.Series] | None:
    raw = read_sql(_BARS_SQL, (day, codes), MINUTE_DB)
    if raw.empty:
        return None
    raw["datetime"] = pd.to_datetime(raw["datetime"])
    t = raw["datetime"].dt.time
    raw = raw[(t >= REGULAR_OPEN) & (t <= REGULAR_CLOSE)]

    bars_by_code = {}
    for code, g in raw.groupby("stock_code", sort=False):
        b = resample_ohlcv(g, tf)
        if len(b) >= 10:
            bars_by_code[code] = b
    if not bars_by_code:
        return None
    return bars_by_code, _market_ret(bars_by_code)


def build(start: str, end: str) -> None:
    codes = load_universe()
    days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()
    CACHE.mkdir(parents=True, exist_ok=True)

    grids = list(itertools.product(LOOKBACKS, DROPS, FORWARDS, ATR_MULTIPLES))
    buffers: dict[tuple, list[pd.DataFrame]] = {}

    for tf in TIMEFRAMES:
        for day in days:
            built = build_day(day, codes, tf)
            if built is None:
                continue
            bars_by_code, mkt = built

            daily = read_sql(_DAILY_SQL, (codes, _to_dash(day)), DAILY_DB)
            amount_by_code = {c: b["amount"].sum() for c, b in bars_by_code.items()}
            rank = pd.Series(amount_by_code).rank(pct=True)

            for code, bars in bars_by_code.items():
                ctx = _daily_context(daily, code, float(bars["open"].iloc[0]))
                if ctx is None or not np.isfinite(ctx["atr14_pct"]):
                    continue
                ctx["amount_rank"] = float(rank[code])
                mret = mkt.reindex(bars["datetime"]).to_numpy()

                for (N, D, M, k_atr) in grids:
                    theta = FIXED_THETA if k_atr is None else k_atr * ctx["atr14_pct"]
                    p = LabelParams(tf, N, D, M, theta)
                    lab = compute_labels(bars, p)
                    cand = lab["is_candidate"] & lab["is_valid"] & (lab["forward_bars"] > 0)
                    if not cand.any():
                        continue

                    feats = compute_features(bars, lab["prior_high"], ctx,
                                             pd.Series(mret), p.lookback_bars)
                    rec = pd.concat([feats[FEATURE_NAMES], lab], axis=1)[cand.to_numpy()]
                    rec["trade_date"] = day
                    rec["stock_code"] = code
                    rec["segment"] = np.where(rec["is_full_lookback"], "full", "partial")
                    rec["atr14_pct"] = ctx["atr14_pct"]
                    rec["market_cap"] = ctx["market_cap"]
                    rec["amount_rank"] = ctx["amount_rank"]
                    rec["theta"] = theta

                    key = (tf, N, D, M, "fixed" if k_atr is None else f"atr{k_atr}")
                    buffers.setdefault(key, []).append(rec)

        _flush(buffers)
        buffers.clear()


def _flush(buffers: dict[tuple, list[pd.DataFrame]]) -> None:
    for key, frames in buffers.items():
        tf, N, D, M, tag = key
        df = pd.concat(frames, ignore_index=True)
        df["atr_quintile"] = pd.qcut(df["atr14_pct"], 5, labels=False, duplicates="drop")
        path = CACHE / f"labels_tf{tf}_N{N}_D{int(D*1000)}_M{M}_{tag}.parquet"
        df.to_parquet(path, index=False)
        print(f"wrote {path.name}: {len(df):,} rows")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20250401")
    ap.add_argument("--end", default="20260709")
    a = ap.parse_args()
    build(a.start, a.end)
```

- [ ] **Step 1b: `build_dataset.py`에 모양 프로브용 이벤트 추출 추가**

Task 7의 `probe_report(events, windows, k)`는 `events`에 `trade_date, hit_up, hit_down, atr14_pct` 컬럼을, `windows`에 `(n, 20)` 배열을 요구한다. **종목-일당 첫 딥드롭 봉 하나만** 취한다 (스펙 8절 이벤트 정의).

`build_dataset.py` 상단에 상수를 추가한다.

```python
SHAPE_TF = 3            # 프로브는 3분봉 고정
SHAPE_N = 60            # 룩백 60분
SHAPE_D = 0.04          # 딥 드롭
SHAPE_M = 60            # 전방 60분
SHAPE_WINDOW = 20       # 직전 20봉
```

`build()`의 종목 루프 안, 격자 루프 **밖**에 다음을 넣는다 (격자마다 반복하면 중복된다).

```python
                if tf == SHAPE_TF:
                    ev = _shape_event(bars, ctx, day, code)
                    if ev is not None:
                        shape_rows.append(ev)
```

`build()` 시작부에 `shape_rows: list[dict] = []`를 선언하고, `_flush(buffers)` 호출 뒤에 `_flush_shape(shape_rows)`를 부른다. `shape_rows`는 TF 루프 전체에 걸쳐 누적되므로 `build()` 최상단에서 한 번만 초기화한다.

```python
def _shape_event(bars: pd.DataFrame, ctx: dict, day: str, code: str) -> dict | None:
    """종목-일당 첫 딥드롭 봉 하나 + 직전 SHAPE_WINDOW 봉 종가."""
    p = LabelParams(SHAPE_TF, SHAPE_N, SHAPE_D, SHAPE_M, FIXED_THETA)
    lab = compute_labels(bars, p)
    cand = (lab["is_candidate"] & lab["is_valid"]
            & (lab["forward_bars"] > 0)).to_numpy()
    if not cand.any():
        return None

    i = int(np.flatnonzero(cand)[0])
    if i < SHAPE_WINDOW:
        return None                      # 직전 20봉이 없으면 버린다

    window = bars["close"].to_numpy(dtype=float)[i - SHAPE_WINDOW:i]
    return {
        "trade_date": day,
        "stock_code": code,
        "hit_up": bool(lab["hit_up"].iloc[i]),
        "hit_down": bool(lab["hit_down"].iloc[i]),
        "atr14_pct": ctx["atr14_pct"],
        **{f"w{j}": window[j] for j in range(SHAPE_WINDOW)},
    }


def _flush_shape(rows: list[dict]) -> None:
    if not rows:
        print("shape events: none")
        return
    df = pd.DataFrame(rows)
    path = CACHE / "events_shape.parquet"
    df.to_parquet(path, index=False)
    print(f"wrote {path.name}: {len(df):,} events")
```

`w0..w19`가 시퀀스다. Task 7 실행 시 `windows = znorm_windows(df[[f'w{j}' for j in range(20)]].to_numpy())`로 복원한다.

**검증:** 스펙 2.3절이 딥드롭 종목-일을 15,699개로 세었다. 전체 기간 실행 후 `events_shape.parquet`의 행 수는 이보다 **작아야 정상**이다 (직전 20봉이 없는 개장 직후 이벤트가 빠지므로). 오히려 크면 종목-일 중복을 의심하고 멈춘다.

- [ ] **Step 1c: 모양 프로브 실행 코드**

```bash
cd D:/tmp/wt-intraday-rebound/RoboTrader_template
python -c "
import pandas as pd
from scripts.discovery.intraday_rebound.shape_probe import probe_report, znorm_windows
df = pd.read_parquet('scripts/discovery/intraday_rebound/_cache/events_shape.parquet')
print('events =', len(df))
w = znorm_windows(df[[f'w{j}' for j in range(20)]].to_numpy())
for k in (8, 10, 12):
    print(f'--- k={k} ---')
    print(probe_report(df, w, k=k).to_string(index=False))
"
```

**판정 (스펙 8절).** 클러스터 간 `up_over_down`이 벌어지고 그 차이가 `mean_atr_pct` 차이로 설명되지 않으면 "모양 정보 있음". 모두 전체 평균 언저리에 뭉치거나, 비의 순서가 `mean_atr_pct`의 순서를 그대로 따라가면 "모양 정보 없음". `ci_lo`/`ci_hi`가 겹치는 클러스터 쌍은 다르다고 말하지 않는다.

- [ ] **Step 2: 스모크 실행 (한 달치)**

Run:
```bash
cd D:/tmp/wt-intraday-rebound/RoboTrader_template
python -m scripts.discovery.intraday_rebound.build_dataset --start 20260601 --end 20260630
```
Expected: `wrote labels_tf3_N60_D25_M60_fixed.parquet: N rows` 형태로 다수 파일. 오류 없이 종료.

행 수가 0인 파일이 있으면 그 격자점은 후보가 없다는 뜻이다. `D=0.08`처럼 극단 조합에서 정상이다.

- [ ] **Step 3: 전체 기간 실행 (백그라운드)**

Run:
```bash
cd D:/tmp/wt-intraday-rebound/RoboTrader_template
nohup python -m scripts.discovery.intraday_rebound.build_dataset \
  --start 20250401 --end 20260709 > _cache/build.log 2>&1 &
```
완료까지 수십 분 예상. `_cache/build.log`로 진행 확인.

- [ ] **Step 4: `report.py` 작성 및 실행**

```python
# scripts/discovery/intraday_rebound/report.py
"""리포트 생성: 격자 통계표 / 낙관편향 간극 / IS-OOS 특징 랭킹 / 모양 프로브.

보고 규칙(스펙 7절): 모든 격자점에서 4개 지표를 항상 한 세트로 낸다.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .features import FEATURE_NAMES
from .ranking import rank_features
from .shape_probe import probe_report, znorm_windows

CACHE = Path(__file__).parent / "_cache"
# parents: [0]=intraday_rebound [1]=discovery [2]=scripts [3]=RoboTrader_template [4]=repo root
REPORT = Path(__file__).resolve().parents[4] / "docs" / "superpowers" / "reports" / \
    "2026-07-09-intraday-rebound-findings.md"

IS_END = "20260131"


def grid_table() -> pd.DataFrame:
    rows = []
    for p in sorted(CACHE.glob("labels_*.parquet")):
        m = re.match(r"labels_tf(\d+)_N(\d+)_D(\d+)_M(\d+)_(\w+)\.parquet", p.name)
        df = pd.read_parquet(p, columns=["hit_up", "hit_down", "hit_close", "mae"])
        if df.empty:
            continue
        pct_up, pct_dn = df["hit_up"].mean(), df["hit_down"].mean()
        rows.append({
            "tf": int(m[1]), "N": int(m[2]), "D": int(m[3]) / 1000,
            "M": int(m[4]), "theta": m[5], "n": len(df),
            "pct_up": round(pct_up * 100, 2),
            "pct_down": round(pct_dn * 100, 2),
            "up_over_down": round(pct_up / pct_dn, 3) if pct_dn > 0 else np.nan,
            "pct_close": round(df["hit_close"].mean() * 100, 2),
            "mae_p10": round(df["mae"].quantile(0.10) * 100, 2),
            "mae_p25": round(df["mae"].quantile(0.25) * 100, 2),
            "mae_p50": round(df["mae"].quantile(0.50) * 100, 2),
        })
    return pd.DataFrame(rows).sort_values("up_over_down", ascending=False)


def is_oos_ranking(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    is_df = df[df["trade_date"] <= IS_END]
    oos_df = df[df["trade_date"] > IS_END]
    if is_df.empty or oos_df.empty:
        return pd.DataFrame()

    r_is = rank_features(is_df, FEATURE_NAMES).set_index("feature")
    r_oos = rank_features(oos_df, FEATURE_NAMES).set_index("feature")
    out = r_is[["directional_auc", "ci_lo", "ci_hi"]].join(
        r_oos[["directional_auc", "ci_lo", "ci_hi"]],
        lsuffix="_is", rsuffix="_oos",
    )
    out["survives"] = (
        (np.sign(out["directional_auc_is"]) == np.sign(out["directional_auc_oos"]))
        & (out["ci_lo_is"] * out["ci_hi_is"] > 0)
        & (out["ci_lo_oos"] * out["ci_hi_oos"] > 0)
    )
    return out.reset_index().sort_values("directional_auc_oos", key=abs, ascending=False)
```

- [ ] **Step 5: 리포트 실행 및 결과 확인**

Run:
```bash
cd D:/tmp/wt-intraday-rebound/RoboTrader_template
python -c "
from scripts.discovery.intraday_rebound.report import grid_table, is_oos_ranking
from pathlib import Path
g = grid_table()
print(g.head(15).to_string(index=False))
best = Path('scripts/discovery/intraday_rebound/_cache/labels_tf3_N60_D40_M60_fixed.parquet')
print(is_oos_ranking(best).to_string(index=False))
"
```

**해석 규칙 (강제).** `survives=False`인 특징은 리포트 결론에 쓰지 않는다. `survives=True`가 하나도 없으면 결론은 **"장중 급락 반등에 예측 가능한 엣지가 없다"**이며, 이는 스펙 12절이 미리 받아들인 유효한 결과다. 숫자를 좋게 만들려고 격자를 더 뒤지지 않는다.

- [ ] **Step 6: 리포트 문서 작성**

`docs/superpowers/reports/2026-07-09-intraday-rebound-findings.md`에 다음 네 절을 실제 출력값으로 채워 작성한다.

1. **격자 통계표** — `grid_table()` 상위 15행. 4개 지표 한 세트.
2. **낙관 편향 간극** — 같은 격자점의 `pct_up`(고가터치) vs `pct_close`(종가). 두 값의 비가 낙관 편향의 크기다.
3. **IS/OOS 특징 랭킹** — `survives` 컬럼 포함. 살아남은 특징만 결론에 인용.
4. **모양 프로브 판정** — `probe_report()` 출력. 클러스터별 `up_over_down`과 `mean_atr_pct`를 나란히. 클러스터 간 비 차이가 ATR 차이로 설명되면 "모양 정보 없음".

각 절 끝에 스펙 2.4절의 유보 사항(단일 기간, 고가터치≠체결, 유니버스 편향)을 재확인한다.

- [ ] **Step 7: 전체 테스트 스위트 + 커밋**

Run:
```bash
cd D:/tmp/wt-intraday-rebound/RoboTrader_template
python -m pytest tests/discovery/intraday_rebound/ -v
python -m pytest tests/ -q 2>&1 | tail -5
```
Expected: 신규 34 passed. 기존 스위트에 **신규 실패 0** (기존 known failure는 그대로).

```bash
cd D:/tmp/wt-intraday-rebound
git add RoboTrader_template/scripts/discovery/intraday_rebound/ docs/superpowers/reports/
git commit -m "feat(discovery): 데이터셋 빌더 + 리포트 (격자/낙관편향/IS-OOS 랭킹/모양 프로브)"
```

---

## Self-Review

**스펙 커버리지**

| 스펙 절 | 구현 태스크 |
|---|---|
| 2.1 유니버스 편향 | Task 1 (`load_universe`, 199 검증) |
| 2.2 비대칭 측정 | Task 3 (`hit_down` 독립 측정), Task 4 (재현 게이트) |
| 2.3 유효 표본 = 날짜 | Task 6 (`date_block_bootstrap_ci`) |
| 4 유니버스·데이터 | Task 1, Task 8 (`MINUTE_DB` / `DAILY_DB` 분리) |
| 5 라벨 정의 + 격자 | Task 3, Task 8 (432 격자점) |
| 5 ATR 정규화 θ | Task 8 (`ATR_MULTIPLES`) |
| 6 특징 6묶음 | Task 5 (18 특징) |
| 7 층화/방향성 AUC | Task 6 |
| 7 IS/OOS 분할 | Task 8 (`is_oos_ranking`, `IS_END`) |
| 8 모양 프로브 | Task 7 (KMeans로 수정) |
| 9 시점 절단 테스트 | Task 5 |
| 9 셔플 테스트 | Task 6 (`test_rank_features_shuffled_labels_collapse_to_zero`) |
| 9 known-answer 테스트 | Task 3 |
| 9 결측봉 미생성 | Task 2 (`test_missing_minutes_do_not_create_bars`) |
| 9 세션 경계 | Task 3 (입력 계약: 한 종목-일) |
| 9 정규장 필터 | Task 4, Task 8 (`_filter_regular_session`) |
| 10 산출물 | Task 8 |
| 11 성공 기준 | Task 8 Step 5 해석 규칙 |

**미커버 (의도적)**
- 스펙 6절 F의 `breadth`: Task 5에서 제외를 명시하고 다음 라운드로 이월 (`market_ret`과 고상관).
- 스펙 6절 D의 시간대 버킷: `minutes_since_open` 연속 변수로 대체, 리포트에서 5분위 표시.

**타입 일관성 확인**
- `LabelParams.lookback_bars` / `forward_bars` — Task 3에서 property로 정의, Task 4·8에서 `p.lookback_bars`로 사용. 일치.
- `compute_features(bars, prior_high, daily_ctx, market_ret, lookback_bars)` — Task 5 정의, Task 8 호출 인자 순서 일치.
- `rank_features(df, feature_names, strata_col='atr_quintile', date_col='trade_date')` — Task 6 정의. Task 8 `_flush`가 `atr_quintile`, `trade_date` 컬럼을 만든다. 일치.
- `date_block_bootstrap_ci(fn, dates, ...)` — Task 6 정의, Task 7 `probe_report`가 재사용. `fn`은 인덱스 배열을 받는다. 일치.
- `probe_report(events, windows, k)` — `events`에 `trade_date, hit_up, hit_down, atr14_pct` 필요. Task 8 Step 1b의 `_shape_event()`가 정확히 이 컬럼들과 `w0..w19`를 만든다. 일치.
- `znorm_windows(seq)` — Task 7 정의, Task 8 Step 1c에서 `df[[f'w{j}' ...]].to_numpy()`로 호출. `(n, 20)` 배열. 일치.

**플레이스홀더 스캔:** 없음. 모든 코드 단계가 실행 가능한 코드를 포함한다. `_daily_context`의 `amount_rank: np.nan`은 미완이 아니라 의도적 2단계 초기화이며, `build()`가 일자별 랭크로 즉시 덮어쓴다.
