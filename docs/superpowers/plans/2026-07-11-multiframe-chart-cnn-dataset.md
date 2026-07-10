# 멀티프레임 차트 CNN — 계획 1: 데이터 파이프라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 3·5·15분봉을 겹친 6채널 정규화 차트 이미지 + 변동성 스칼라 + 3거래일 TP/SL 라벨을, 199종목 고정 유니버스 전 시점에서 생성해 디스크 캐시로 저장하는 결정적 파이프라인을 만든다.

**Architecture:** 직전 `intraday_rebound` 모듈(db/resample/universe/first_touch)을 최대 재사용한다. 신규 핵심은 **날짜 경계를 넘는 3거래일 라벨러**(오버나잇 갭을 다음날 시가로 실현)와 **결정적 멀티프레임 래스터화**다. 모든 신규 순수함수는 픽셀/값 단위 테스트로 고정한다. 모델 학습과 워크포워드는 계획 2에서 다룬다.

**Tech Stack:** Python 3.8+ 호환, numpy, pandas, psycopg2 (읽기전용), parquet(pyarrow). PyTorch는 계획 2에서만.

## Global Constraints

- 연구 전용. **라이브 코드(`core/` `bot/` `framework/` `api/` `strategies/` `collectors/` `db/` `runners/` `signals/` `utils/` `tools/`) 절대 수정 금지.** 신규 코드는 전부 `scripts/discovery/multiframe_chart_cnn/` 아래.
- DB 접근은 **읽기전용**. 기존 `scripts/discovery/intraday_rebound/db.py`의 `read_sql(sql, params, dbname)` / `MINUTE_DB` 재사용. 새 커넥터 만들지 말 것.
- 유니버스는 **199종목 고정**. `intraday_rebound/universe.py::load_frozen_universe()` 재사용. `load_universe()`(DB 라이브 조회) 금지.
- 데이터 소스: `kis_template.minute_candles` (host 127.0.0.1, port 5433, user robotrader, pw 1234). SSOT. `adj_factor` 곱하지 말 것.
- 정규장만: 09:00:00 ≤ time ≤ 15:30:00.
- 유효 표본 단위 = **거래일**(봉 아님). 층화/추출/폴드 경계는 항상 거래일 기준.
- 테스트 위치: `tests/discovery/multiframe_chart_cnn/test_*.py`. 실행은 repo 루트가 아니라 `RoboTrader_template/`에서 `python -m pytest`.
- 성패 기준선(사후 조정 금지, 계획 2에서 판정): net > +0.05%, gross ≥ 0.26%, 왕복비용 0.21% (`config/constants.py:118-119`).
- 브랜치: `feat/multiframe-chart-cnn` (미푸시). 커밋만, push는 사용자 승인 후.
- 결정성: 모든 래스터화/라벨 함수는 순수함수 — 같은 입력 → 같은 출력. `Date.now`/난수 금지.

---

### Task 1: 예산 스파이크 — 표본 규모·라벨 도달률·캐시 용량 실측 (게이팅)

이 태스크는 TDD가 아니라 **측정**이다. 산출된 숫자가 표본 추출률과 이미지 캐시 설계를 확정한다. **이 태스크 종료 후 반드시 사용자 리뷰 체크포인트.**

**Files:**
- Create: `RoboTrader_template/scripts/discovery/multiframe_chart_cnn/__init__.py` (빈 파일)
- Create: `RoboTrader_template/scripts/discovery/multiframe_chart_cnn/budget_spike.py`

**Interfaces:**
- Consumes: `intraday_rebound.db.read_sql`, `intraday_rebound.universe.load_frozen_universe`, `intraday_rebound.resample.resample_ohlcv`
- Produces: stdout 리포트만 (다음 태스크가 코드로 의존하지 않음)

- [ ] **Step 1: `__init__.py` 생성 (빈 파일)**

```bash
touch RoboTrader_template/scripts/discovery/multiframe_chart_cnn/__init__.py
```

- [ ] **Step 2: 스파이크 스크립트 작성**

`budget_spike.py`:

```python
# scripts/discovery/multiframe_chart_cnn/budget_spike.py
"""예산 스파이크: 5거래일 슬라이스에서 표본 규모/라벨 도달률/캐시 용량을 실측한다.

TDD 아님 — 측정 스크립트. 출력 숫자로 표본 추출률과 캐시 설계를 확정한다.
결과는 사용자 리뷰 체크포인트에서 검토한다.
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

from scripts.discovery.intraday_rebound.db import MINUTE_DB, read_sql
from scripts.discovery.intraday_rebound.resample import resample_ohlcv
from scripts.discovery.intraday_rebound.universe import load_frozen_universe

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
DECISION_START = pd.Timestamp("10:00:00").time()   # 09:00~10:00 룩백 부족 제외
LOOKBACK_BARS_15M = 60                              # 15분봉 60봉 = 가장 긴 룩백 요구


def spike(start: str, end: str) -> None:
    codes = load_frozen_universe()
    days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()
    print(f"universe={len(codes)} days={len(days)} ({days[0]}..{days[-1]})")

    total_candidate_points = 0
    total_stock_days = 0
    t0 = time.time()
    for day in days:
        raw = read_sql(_BARS_SQL, (day, codes), MINUTE_DB)
        if raw.empty:
            continue
        raw["datetime"] = pd.to_datetime(raw["datetime"])
        t = raw["datetime"].dt.time
        raw = raw[(t >= REGULAR_OPEN) & (t <= REGULAR_CLOSE)]
        for code, g in raw.groupby("stock_code", sort=False):
            bars3 = resample_ohlcv(g, 3)
            bars15 = resample_ohlcv(g, 15)
            # 15분봉 60봉을 채우려면 15*60=900분 룩백 필요 → 하루 안에선 불충분.
            # 여기서는 "하루 내 유효 3분봉 시점(10:00 이후, 15:30 마감 60분 전까지)" 만 센다.
            tt = bars3["datetime"].dt.time
            valid = bars3[(tt >= DECISION_START)]
            total_candidate_points += max(0, len(valid) - 20)  # 마감 근처 대략 20봉 제외
            total_stock_days += 1

    dt = time.time() - t0
    print(f"stock-days={total_stock_days} candidate_points(1day-approx)={total_candidate_points}")
    print(f"extract_time_5day={dt:.1f}s  -> full 356day est={dt/len(days)*356/60:.1f}min")
    # 6ch x 64x64 float32 = 6*64*64*4 = 98,304 bytes/image. int8 로 저장하면 1/4.
    bytes_per_img_f32 = 6 * 64 * 64 * 4
    bytes_per_img_i8 = 6 * 64 * 64 * 1
    full_est = total_candidate_points / len(days) * 356
    print(f"full_points_est={full_est:,.0f}")
    print(f"cache_f32={full_est*bytes_per_img_f32/1e9:.1f}GB  cache_i8={full_est*bytes_per_img_i8/1e9:.1f}GB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20260601")
    ap.add_argument("--end", default="20260607")
    args = ap.parse_args()
    spike(args.start, args.end)
```

- [ ] **Step 3: 5거래일 슬라이스로 실행**

Run (working dir = `RoboTrader_template/`):
```bash
PYTHONPATH=. python -m scripts.discovery.multiframe_chart_cnn.budget_spike --start 20260601 --end 20260607
```
Expected: `universe=199`, candidate_points/cache_i8/cache_f32/extract_time 숫자 출력. 크래시 없이 완료.

- [ ] **Step 4: 커밋**

```bash
git add RoboTrader_template/scripts/discovery/multiframe_chart_cnn/__init__.py \
        RoboTrader_template/scripts/discovery/multiframe_chart_cnn/budget_spike.py
git commit -m "spike(mfcnn): 표본 규모/캐시 용량 예산 측정 스크립트"
```

- [ ] **Step 5: STOP — 사용자 리뷰 체크포인트**

출력한 `full_points_est`, `cache_i8`(예상 GB), `extract_time` 356일 환산치를 사용자에게 보고한다. 표본이 너무 크면(예: cache_i8 > 50GB) **날짜 층화 추출률**을 여기서 결정한다. 사용자 승인 전에는 Task 2로 넘어가지 않는다.

---

### Task 2: 3거래일 라벨러 — 날짜 경계 통과 + 오버나잇 갭 실현

새 설계의 심장. 진입 다음 3분봉 시가로 진입, 이후 **3거래일** 안에 TP/SL 선착을 1분봉 해상도로 판정한다. 기존 `outcome_from_path`는 하루 안에서만 동작하고 갭쓰루를 theta로 낙관 실현하므로 재사용하지 않고, 갭을 정직하게 실현하는 새 함수를 만든다.

**Files:**
- Create: `RoboTrader_template/scripts/discovery/multiframe_chart_cnn/label3d.py`
- Test: `RoboTrader_template/tests/discovery/multiframe_chart_cnn/__init__.py` (빈 파일)
- Test: `RoboTrader_template/tests/discovery/multiframe_chart_cnn/test_label3d.py`

**Interfaces:**
- Consumes: 없음 (순수 함수, numpy 배열만 받음)
- Produces:
  - `label_3day(entry_open: float, fwd_high: np.ndarray, fwd_low: np.ndarray, fwd_open: np.ndarray, fwd_close: np.ndarray, tp: float, sl: float) -> tuple[str, float]`
    - 반환 `(outcome, realized_ret)`. outcome ∈ {"tp","sl","timeout"}. realized_ret = 실현 수익률(비용 차감 전).
    - 진입가 = `entry_open`. 전방 1분봉들을 순서대로 스캔.
    - TP 목표 = `entry_open*(1+tp)`, SL 목표 = `entry_open*(1-sl)`.
    - 각 봉에서: **먼저 갭 판정** — `fwd_open[j] >= tp_target` 이면 TP를 시가에 실현(`realized_ret = fwd_open[j]/entry_open - 1`, gap-up through). `fwd_open[j] <= sl_target` 이면 SL을 시가에 실현(gap-down through). 둘 다 아니면 봉 내 고저로 판정: `fwd_high[j] >= tp_target` → TP를 정확히 `tp`에 실현(`realized_ret = tp`), `fwd_low[j] <= sl_target` → SL을 정확히 `-sl`에 실현(`realized_ret = -sl`). 한 봉이 시가 기준 TP·SL을 동시에 만족할 순 없음(시가는 한 값). 봉 내 고저가 양쪽을 다 건드리면 **SL 우선(보수적)**.
    - 아무것도 못 건드리면 `("timeout", fwd_close[-1]/entry_open - 1)`.

- [ ] **Step 1: 테스트 디렉토리 `__init__.py` 생성**

```bash
touch RoboTrader_template/tests/discovery/multiframe_chart_cnn/__init__.py
```

- [ ] **Step 2: 실패 테스트 작성**

`test_label3d.py`:

```python
import numpy as np
import pytest

from scripts.discovery.multiframe_chart_cnn.label3d import label3d


def test_tp_hit_intrabar_realizes_exactly_at_tp():
    entry = 100.0
    # 1봉째 고가가 +3% 넘게 찍히지만 시가는 갭 아님 → 정확히 tp 에 실현
    fwd_open = np.array([100.1, 100.2])
    fwd_high = np.array([103.5, 104.0])
    fwd_low = np.array([99.9, 100.0])
    fwd_close = np.array([103.0, 103.5])
    outcome, ret = label3d(entry, fwd_high, fwd_low, fwd_open, fwd_close, tp=0.03, sl=0.03)
    assert outcome == "tp"
    assert ret == pytest.approx(0.03)


def test_gap_up_through_tp_realizes_at_open():
    entry = 100.0
    # 시가가 이미 +5% 갭업 → tp 를 시가에 실현(정확히 3% 아님, 5%)
    fwd_open = np.array([105.0])
    fwd_high = np.array([106.0])
    fwd_low = np.array([104.0])
    fwd_close = np.array([105.5])
    outcome, ret = label3d(entry, fwd_high, fwd_low, fwd_open, fwd_close, tp=0.03, sl=0.03)
    assert outcome == "tp"
    assert ret == pytest.approx(0.05)


def test_gap_down_through_sl_realizes_at_open():
    entry = 100.0
    fwd_open = np.array([94.0])   # -6% 갭다운
    fwd_high = np.array([95.0])
    fwd_low = np.array([93.0])
    fwd_close = np.array([94.5])
    outcome, ret = label3d(entry, fwd_high, fwd_low, fwd_open, fwd_close, tp=0.05, sl=0.03)
    assert outcome == "sl"
    assert ret == pytest.approx(-0.06)


def test_intrabar_both_barriers_sl_wins():
    entry = 100.0
    fwd_open = np.array([100.0])
    fwd_high = np.array([104.0])   # +4% 고가
    fwd_low = np.array([96.0])     # -4% 저가 (같은 봉)
    fwd_close = np.array([100.0])
    outcome, ret = label3d(entry, fwd_high, fwd_low, fwd_open, fwd_close, tp=0.03, sl=0.03)
    assert outcome == "sl"
    assert ret == pytest.approx(-0.03)


def test_timeout_realizes_at_last_close():
    entry = 100.0
    fwd_open = np.array([100.0, 100.5, 101.0])
    fwd_high = np.array([101.0, 101.5, 102.0])
    fwd_low = np.array([99.0, 99.5, 100.0])
    fwd_close = np.array([100.5, 101.0, 101.5])
    outcome, ret = label3d(entry, fwd_high, fwd_low, fwd_open, fwd_close, tp=0.05, sl=0.05)
    assert outcome == "timeout"
    assert ret == pytest.approx(101.5 / 100.0 - 1.0)


def test_first_touch_ordering_sl_before_tp():
    entry = 100.0
    # 1봉 SL, 2봉 TP → 먼저 온 SL 이 결과
    fwd_open = np.array([100.0, 100.0])
    fwd_high = np.array([101.0, 105.0])
    fwd_low = np.array([96.0, 100.0])
    fwd_close = np.array([97.0, 104.0])
    outcome, ret = label3d(entry, fwd_high, fwd_low, fwd_open, fwd_close, tp=0.03, sl=0.03)
    assert outcome == "sl"
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd RoboTrader_template && PYTHONPATH=. python -m pytest tests/discovery/multiframe_chart_cnn/test_label3d.py -v`
Expected: FAIL — `ImportError: cannot import name 'label3d'`

- [ ] **Step 4: 구현 작성**

`label3d.py`:

```python
# scripts/discovery/multiframe_chart_cnn/label3d.py
"""3거래일 triple-barrier 라벨러. 날짜 경계를 넘는 전방 1분봉 경로를 받아
TP/SL 선착을 판정하고, 오버나잇 갭은 다음 봉 시가로 정직하게 실현한다.

기존 intraday_rebound.outcome_from_path 와 다른 점:
  - 갭쓰루를 theta 로 낙관 실현하지 않고, 그 봉의 시가로 실현한다(realized_ret).
  - 결과 라벨이 tp/sl/timeout (3-class) 이다.
"""
from __future__ import annotations

import numpy as np


def label3d(entry_open: float,
            fwd_high: np.ndarray, fwd_low: np.ndarray,
            fwd_open: np.ndarray, fwd_close: np.ndarray,
            tp: float, sl: float) -> tuple[str, float]:
    fwd_high = np.asarray(fwd_high, dtype=float)
    fwd_low = np.asarray(fwd_low, dtype=float)
    fwd_open = np.asarray(fwd_open, dtype=float)
    fwd_close = np.asarray(fwd_close, dtype=float)

    n = min(len(fwd_high), len(fwd_low), len(fwd_open), len(fwd_close))
    tp_target = entry_open * (1.0 + tp)
    sl_target = entry_open * (1.0 - sl)

    for j in range(n):
        o = fwd_open[j]
        # 갭 우선: 시가가 이미 배리어를 넘었으면 시가에 실현.
        if o <= sl_target:
            return "sl", o / entry_open - 1.0
        if o >= tp_target:
            return "tp", o / entry_open - 1.0
        # 봉 내 고저. 양쪽 다 건드리면 SL 우선(보수적).
        if fwd_low[j] <= sl_target:
            return "sl", -sl
        if fwd_high[j] >= tp_target:
            return "tp", tp
    if n == 0:
        return "timeout", 0.0
    return "timeout", fwd_close[n - 1] / entry_open - 1.0
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd RoboTrader_template && PYTHONPATH=. python -m pytest tests/discovery/multiframe_chart_cnn/test_label3d.py -v`
Expected: 6 passed

- [ ] **Step 6: 커밋**

```bash
git add RoboTrader_template/scripts/discovery/multiframe_chart_cnn/label3d.py \
        RoboTrader_template/tests/discovery/multiframe_chart_cnn/
git commit -m "feat(mfcnn): 3거래일 갭실현 triple-barrier 라벨러 + 테스트"
```

---

### Task 3: 전방경로 조립기 — 종목별 다일 1분봉에서 3거래일 창 잘라내기

라벨러(Task 2)에 넣을 `fwd_*` 배열을, 한 종목의 여러 거래일 1분봉과 진입 시각으로부터 만든다. 날짜 경계를 넘어 3거래일치를 이어붙인다.

**Files:**
- Create: `RoboTrader_template/scripts/discovery/multiframe_chart_cnn/forward_path.py`
- Test: `RoboTrader_template/tests/discovery/multiframe_chart_cnn/test_forward_path.py`

**Interfaces:**
- Consumes: 없음 (순수 함수)
- Produces:
  - `build_forward_path(day_bars: dict[str, pd.DataFrame], entry_day: str, entry_dt: pd.Timestamp, horizon_days: int = 3) -> tuple[float, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None`
    - `day_bars`: `{trade_date(str): 1분봉 DataFrame(datetime,open,high,low,close,volume,amount, datetime 정렬)}`. 정규장만.
    - `entry_dt`: 진입 **결정** 시각(3분봉 마감 시각). 진입 체결 = `entry_day`에서 `entry_dt` **직후 1분봉의 시가**.
    - 반환 `(entry_open, fwd_high, fwd_low, fwd_open, fwd_close)`. 전방 = 진입 체결 봉부터 시작해 `entry_day` 포함 연속 `horizon_days` 거래일의 끝까지의 1분봉들(진입 체결 봉 제외한 이후 경로가 아니라, **체결 봉의 open 이 entry_open 이고 fwd 배열은 체결 봉 다음 1분봉부터**).
    - `entry_dt` 직후 1분봉이 없으면(그날 마지막 봉이 진입 결정 시각) 다음 거래일 첫 봉을 체결로 사용. 전방 거래일이 `horizon_days` 만큼 없으면 있는 데까지 사용(말미 절단). 체결 봉 자체가 없으면(데이터 완전 부재) `None`.

- [ ] **Step 1: 실패 테스트 작성**

`test_forward_path.py`:

```python
import numpy as np
import pandas as pd
import pytest

from scripts.discovery.multiframe_chart_cnn.forward_path import build_forward_path


def _mk_day(date: str, prices: list[float]) -> pd.DataFrame:
    # 09:00 부터 1분봉, open=high=low=close=price 로 단순화
    base = pd.Timestamp(f"{date[:4]}-{date[4:6]}-{date[6:]} 09:00:00")
    dts = [base + pd.Timedelta(minutes=i) for i in range(len(prices))]
    p = np.array(prices, dtype=float)
    return pd.DataFrame({"datetime": dts, "open": p, "high": p, "low": p,
                         "close": p, "volume": 1.0, "amount": p})


def test_entry_fill_is_next_minute_open_same_day():
    d1 = _mk_day("20260601", [100, 101, 102, 103, 104])
    day_bars = {"20260601": d1}
    entry_dt = d1["datetime"].iloc[1]  # 09:01 결정 → 체결 = 09:02 시가 = 102
    res = build_forward_path(day_bars, "20260601", entry_dt, horizon_days=1)
    assert res is not None
    entry_open, fh, fl, fo, fc = res
    assert entry_open == pytest.approx(102.0)
    # fwd 는 체결봉(09:02) 다음(09:03)부터
    assert fo[0] == pytest.approx(103.0)
    assert len(fh) == 2  # 09:03, 09:04


def test_forward_crosses_into_next_trading_days():
    d1 = _mk_day("20260601", [100, 101])
    d2 = _mk_day("20260602", [110, 111])
    d3 = _mk_day("20260603", [120, 121])
    day_bars = {"20260601": d1, "20260602": d2, "20260603": d3}
    entry_dt = d1["datetime"].iloc[0]  # 09:00 결정 → 체결 09:01 = 101
    res = build_forward_path(day_bars, "20260601", entry_dt, horizon_days=3)
    entry_open, fh, fl, fo, fc = res
    assert entry_open == pytest.approx(101.0)
    # 다음날 시가 110 이 fwd_open 에 포함 → 갭 반영 확인
    assert 110.0 in fo
    assert 120.0 in fo


def test_entry_at_last_bar_fills_next_day_open():
    d1 = _mk_day("20260601", [100, 101])   # 마지막봉 09:01
    d2 = _mk_day("20260602", [110, 111])
    day_bars = {"20260601": d1, "20260602": d2}
    entry_dt = d1["datetime"].iloc[1]  # 09:01(그날 마지막) 결정 → 체결 = 다음날 첫봉 110
    res = build_forward_path(day_bars, "20260601", entry_dt, horizon_days=3)
    entry_open, fh, fl, fo, fc = res
    assert entry_open == pytest.approx(110.0)


def test_missing_fill_returns_none():
    d1 = _mk_day("20260601", [100])
    day_bars = {"20260601": d1}
    entry_dt = d1["datetime"].iloc[0]  # 그날 마지막봉이자 유일봉, 다음날 없음
    res = build_forward_path(day_bars, "20260601", entry_dt, horizon_days=3)
    assert res is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd RoboTrader_template && PYTHONPATH=. python -m pytest tests/discovery/multiframe_chart_cnn/test_forward_path.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: 구현 작성**

`forward_path.py`:

```python
# scripts/discovery/multiframe_chart_cnn/forward_path.py
"""진입 시각으로부터 3거래일 전방 1분봉 경로를 조립한다(날짜 경계 통과).

계약: day_bars 의 각 값은 한 종목-일의 정규장 1분봉(datetime 오름차순).
진입 체결 = 결정 시각 직후 1분봉의 시가. 그 봉이 없으면 다음 거래일 첫 봉.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_forward_path(day_bars: dict, entry_day: str, entry_dt: pd.Timestamp,
                       horizon_days: int = 3):
    days = sorted(day_bars.keys())
    if entry_day not in day_bars:
        return None
    start_i = days.index(entry_day)
    window_days = days[start_i:start_i + horizon_days]

    # 창 전체 1분봉을 시간순으로 이어붙인다.
    frames = [day_bars[d].sort_values("datetime", kind="mergesort") for d in window_days]
    cat = pd.concat(frames, ignore_index=True)
    dts = pd.to_datetime(cat["datetime"]).to_numpy()

    # 체결 봉 = entry_dt 보다 datetime 이 큰 첫 봉.
    after = np.where(dts > np.datetime64(entry_dt))[0]
    if after.size == 0:
        return None
    fill_i = int(after[0])

    o = cat["open"].to_numpy(dtype=float)
    h = cat["high"].to_numpy(dtype=float)
    l = cat["low"].to_numpy(dtype=float)
    c = cat["close"].to_numpy(dtype=float)

    entry_open = float(o[fill_i])
    fwd_open = o[fill_i + 1:]
    fwd_high = h[fill_i + 1:]
    fwd_low = l[fill_i + 1:]
    fwd_close = c[fill_i + 1:]
    return entry_open, fwd_high, fwd_low, fwd_open, fwd_close
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd RoboTrader_template && PYTHONPATH=. python -m pytest tests/discovery/multiframe_chart_cnn/test_forward_path.py -v`
Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/scripts/discovery/multiframe_chart_cnn/forward_path.py \
        RoboTrader_template/tests/discovery/multiframe_chart_cnn/test_forward_path.py
git commit -m "feat(mfcnn): 3거래일 전방경로 조립기(날짜경계 통과) + 테스트"
```

---

### Task 4: 멀티프레임 래스터화 — 6채널 64×64 정규화 이미지

결정적 순수함수. 진입 시각까지의 1분봉으로 3/5/15분봉 각 최근 60봉을 그려 6채널 배열을 만든다. **정규화가 사활** — 각 채널 세로축은 그 60봉 구간 자체의 값으로 0~1.

**Files:**
- Create: `RoboTrader_template/scripts/discovery/multiframe_chart_cnn/rasterize.py`
- Test: `RoboTrader_template/tests/discovery/multiframe_chart_cnn/test_rasterize.py`

**Interfaces:**
- Consumes: `intraday_rebound.resample.resample_ohlcv`
- Produces:
  - `render_frame(bars: pd.DataFrame, n_bars: int = 60, size: int = 64) -> np.ndarray`
    - 입력: 한 종목의 N분봉(datetime,open,high,low,close,volume) 오름차순, 진입 시각 이하 봉만.
    - 마지막 `n_bars` 봉을 취해 `(2, size, size)` float32 배열 반환. ch0=가격, ch1=거래량. 값 0~1.
    - 가격 세로축: 그 `n_bars` 봉의 `min(low)`~`max(high)` 로 0~1 정규화. 가로: 봉 순서를 `size` 칸에 매핑(봉 수 < size 면 왼쪽부터, 오른쪽 정렬). 각 봉은 고가~저가 세로 스팬을 채우고, 몸통(open~close)은 값 1.0(양봉)/0.6(음봉), 심지는 0.3.
    - 거래량 세로축: 그 `n_bars` 봉의 `max(volume)` 로 0~1. 막대는 바닥에서 위로.
    - 봉이 0개면 전부 0 배열.
  - `render_multiframe(minute_bars: pd.DataFrame, n_bars: int = 60, size: int = 64) -> np.ndarray`
    - 입력: 진입 시각까지의 **1분봉**. 내부에서 3/5/15분봉으로 리샘플 후 각 `render_frame`.
    - 반환 `(6, size, size)` float32: [price3, vol3, price5, vol5, price15, vol15].

- [ ] **Step 1: 실패 테스트 작성**

`test_rasterize.py`:

```python
import numpy as np
import pandas as pd
import pytest

from scripts.discovery.multiframe_chart_cnn.rasterize import render_frame, render_multiframe


def _mk_bars(prices, vols=None):
    n = len(prices)
    base = pd.Timestamp("2026-06-01 09:00:00")
    dts = [base + pd.Timedelta(minutes=i) for i in range(n)]
    p = np.array(prices, dtype=float)
    v = np.array(vols if vols is not None else [1.0] * n, dtype=float)
    # 단순화: high=price*1.001, low=price*0.999, open=close=price
    return pd.DataFrame({"datetime": dts, "open": p, "high": p * 1.001,
                         "low": p * 0.999, "close": p, "volume": v, "amount": p * v})


def test_render_frame_shape_and_range():
    bars = _mk_bars(list(range(100, 200)))
    img = render_frame(bars, n_bars=60, size=64)
    assert img.shape == (2, 64, 64)
    assert img.dtype == np.float32
    assert img.min() >= 0.0 and img.max() <= 1.0


def test_price_normalization_is_scale_invariant():
    # 같은 모양, 다른 절대가격 → 동일 이미지여야 한다(종목 정체성 소거).
    bars_a = _mk_bars([100, 110, 105, 120, 115] * 12)
    bars_b = _mk_bars([1000, 1100, 1050, 1200, 1150] * 12)
    img_a = render_frame(bars_a, n_bars=60, size=64)
    img_b = render_frame(bars_b, n_bars=60, size=64)
    np.testing.assert_allclose(img_a, img_b, atol=1e-6)


def test_volume_normalization_is_scale_invariant():
    shape = [100, 110, 105, 120, 115] * 12
    bars_a = _mk_bars(shape, vols=[10, 20, 15, 30, 25] * 12)
    bars_b = _mk_bars(shape, vols=[1000, 2000, 1500, 3000, 2500] * 12)
    img_a = render_frame(bars_a, n_bars=60, size=64)
    img_b = render_frame(bars_b, n_bars=60, size=64)
    np.testing.assert_allclose(img_a[1], img_b[1], atol=1e-6)


def test_empty_bars_all_zero():
    empty = _mk_bars([]).iloc[0:0]
    img = render_frame(empty, n_bars=60, size=64)
    assert img.shape == (2, 64, 64)
    assert np.all(img == 0.0)


def test_render_multiframe_six_channels():
    # 1분봉 900개(15분봉 60봉 확보) 필요
    bars1m = _mk_bars(list(np.linspace(100, 200, 900)))
    img = render_multiframe(bars1m, n_bars=60, size=64)
    assert img.shape == (6, 64, 64)
    assert img.dtype == np.float32
    assert img.min() >= 0.0 and img.max() <= 1.0


def test_render_multiframe_deterministic():
    bars1m = _mk_bars(list(np.linspace(100, 200, 900)))
    a = render_multiframe(bars1m)
    b = render_multiframe(bars1m)
    np.testing.assert_array_equal(a, b)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd RoboTrader_template && PYTHONPATH=. python -m pytest tests/discovery/multiframe_chart_cnn/test_rasterize.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: 구현 작성**

`rasterize.py`:

```python
# scripts/discovery/multiframe_chart_cnn/rasterize.py
"""결정적 멀티프레임 래스터화. 3/5/15분봉 각 60봉을 64x64 로 그려 6채널 텐서.

정규화가 사활: 각 채널 세로축은 그 60봉 구간 자체의 값으로 0~1. 절대 가격·
절대 거래량·종목 정체성이 이미지에서 완전히 소거된다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.discovery.intraday_rebound.resample import resample_ohlcv

BODY_UP = 1.0
BODY_DN = 0.6
WICK = 0.3


def _y(value: float, lo: float, hi: float, size: int) -> int:
    if hi <= lo:
        return size // 2
    frac = (value - lo) / (hi - lo)
    frac = min(max(frac, 0.0), 1.0)
    # y=0 을 위(고가)로: 이미지 좌표계 위쪽이 큰 값
    return int(round((1.0 - frac) * (size - 1)))


def render_frame(bars: pd.DataFrame, n_bars: int = 60, size: int = 64) -> np.ndarray:
    img = np.zeros((2, size, size), dtype=np.float32)
    if bars is None or len(bars) == 0:
        return img

    b = bars.tail(n_bars)
    o = b["open"].to_numpy(dtype=float)
    h = b["high"].to_numpy(dtype=float)
    l = b["low"].to_numpy(dtype=float)
    c = b["close"].to_numpy(dtype=float)
    v = b["volume"].to_numpy(dtype=float)
    m = len(b)

    lo, hi = float(np.min(l)), float(np.max(h))
    vmax = float(np.max(v)) if np.max(v) > 0 else 1.0

    # 오른쪽 정렬: 마지막 봉이 가장 오른쪽 칸.
    x_off = size - m if m < size else 0
    # 봉 수 > size 면 마지막 size 개만(tail 이미 n_bars=60<=64 보장하나 방어)
    for k in range(m):
        x = x_off + k
        if x < 0 or x >= size:
            continue
        # 심지: 고가~저가
        y_hi = _y(h[k], lo, hi, size)
        y_lo = _y(l[k], lo, hi, size)
        img[0, y_hi:y_lo + 1, x] = np.maximum(img[0, y_hi:y_lo + 1, x], WICK)
        # 몸통: open~close
        y_o = _y(o[k], lo, hi, size)
        y_c = _y(c[k], lo, hi, size)
        top, bot = min(y_o, y_c), max(y_o, y_c)
        body_val = BODY_UP if c[k] >= o[k] else BODY_DN
        img[0, top:bot + 1, x] = body_val
        # 거래량: 바닥에서 위로
        vfrac = v[k] / vmax
        vh = int(round(vfrac * (size - 1)))
        if vh > 0:
            img[1, size - vh:size, x] = vfrac
    return img


def render_multiframe(minute_bars: pd.DataFrame, n_bars: int = 60,
                      size: int = 64) -> np.ndarray:
    out = np.zeros((6, size, size), dtype=np.float32)
    for fi, tf in enumerate((3, 5, 15)):
        frame = render_frame(resample_ohlcv(minute_bars, tf), n_bars, size)
        out[2 * fi] = frame[0]
        out[2 * fi + 1] = frame[1]
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd RoboTrader_template && PYTHONPATH=. python -m pytest tests/discovery/multiframe_chart_cnn/test_rasterize.py -v`
Expected: 6 passed

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/scripts/discovery/multiframe_chart_cnn/rasterize.py \
        RoboTrader_template/tests/discovery/multiframe_chart_cnn/test_rasterize.py
git commit -m "feat(mfcnn): 6채널 정규화 멀티프레임 래스터화 + 스케일불변 테스트"
```

---

### Task 5: 변동성 스칼라 — 정규화가 지운 크기 정보 복원

이미지 정규화가 지우는 "구간이 얼마나 크게 움직였나"를 스칼라 2개로 보존해 모델 마지막 층에 넣는다.

**Files:**
- Create: `RoboTrader_template/scripts/discovery/multiframe_chart_cnn/scalars.py`
- Test: `RoboTrader_template/tests/discovery/multiframe_chart_cnn/test_scalars.py`

**Interfaces:**
- Consumes: 없음 (순수 함수)
- Produces:
  - `vol_scalars(bars3: pd.DataFrame, n_bars: int = 60) -> np.ndarray`
    - 입력: 진입 시각까지의 3분봉(최근 `n_bars` 사용).
    - 반환 `(2,)` float32: `[lookback_range_pct, atr_pct]`.
    - `lookback_range_pct = (max(high)-min(low)) / last_close`.
    - `atr_pct = mean(high-low) / last_close` (단순 ATR 근사, 최근 n_bars).
    - 봉 0개면 `[0,0]`.

- [ ] **Step 1: 실패 테스트 작성**

`test_scalars.py`:

```python
import numpy as np
import pandas as pd
import pytest

from scripts.discovery.multiframe_chart_cnn.scalars import vol_scalars


def _mk(prices, highs=None, lows=None):
    n = len(prices)
    base = pd.Timestamp("2026-06-01 09:00:00")
    dts = [base + pd.Timedelta(minutes=3 * i) for i in range(n)]
    p = np.array(prices, dtype=float)
    return pd.DataFrame({"datetime": dts, "open": p,
                         "high": np.array(highs, float) if highs else p,
                         "low": np.array(lows, float) if lows else p,
                         "close": p, "volume": 1.0, "amount": p})


def test_range_pct():
    bars = _mk([100, 120, 90, 110], highs=[100, 120, 90, 110], lows=[100, 120, 90, 110])
    s = vol_scalars(bars, n_bars=60)
    assert s.shape == (2,)
    # range = 120-90=30, last_close=110 → 0.2727
    assert s[0] == pytest.approx(30 / 110)


def test_atr_pct():
    bars = _mk([100, 100], highs=[102, 104], lows=[98, 100])
    s = vol_scalars(bars, n_bars=60)
    # mean(high-low) = mean(4,4)=4, last_close=100 → 0.04
    assert s[1] == pytest.approx(0.04)


def test_empty_zero():
    empty = _mk([]).iloc[0:0]
    s = vol_scalars(empty)
    assert np.all(s == 0.0)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd RoboTrader_template && PYTHONPATH=. python -m pytest tests/discovery/multiframe_chart_cnn/test_scalars.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: 구현 작성**

`scalars.py`:

```python
# scripts/discovery/multiframe_chart_cnn/scalars.py
"""변동성 보조 스칼라. 이미지 정규화가 지운 절대 변동폭을 모델에 복원해 준다."""
from __future__ import annotations

import numpy as np
import pandas as pd


def vol_scalars(bars3: pd.DataFrame, n_bars: int = 60) -> np.ndarray:
    if bars3 is None or len(bars3) == 0:
        return np.zeros(2, dtype=np.float32)
    b = bars3.tail(n_bars)
    high = b["high"].to_numpy(dtype=float)
    low = b["low"].to_numpy(dtype=float)
    close = b["close"].to_numpy(dtype=float)
    last = float(close[-1])
    if last == 0:
        return np.zeros(2, dtype=np.float32)
    range_pct = (float(np.max(high)) - float(np.min(low))) / last
    atr_pct = float(np.mean(high - low)) / last
    return np.array([range_pct, atr_pct], dtype=np.float32)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd RoboTrader_template && PYTHONPATH=. python -m pytest tests/discovery/multiframe_chart_cnn/test_scalars.py -v`
Expected: 3 passed

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/scripts/discovery/multiframe_chart_cnn/scalars.py \
        RoboTrader_template/tests/discovery/multiframe_chart_cnn/test_scalars.py
git commit -m "feat(mfcnn): 변동성 보조 스칼라(range/atr) + 테스트"
```

---

### Task 6: 데이터셋 추출기 — 전 시점 순회해 (이미지·스칼라·라벨·메타) 캐시 생성

앞선 순수함수들을 엮어 199종목 × 전 거래일 × 유효 시점을 순회하며 샘플을 만들고 디스크에 저장한다. Task 1 스파이크가 정한 **날짜 층화 추출률**을 여기서 적용한다.

**Files:**
- Create: `RoboTrader_template/scripts/discovery/multiframe_chart_cnn/build_dataset.py`
- Test: `RoboTrader_template/tests/discovery/multiframe_chart_cnn/test_build_dataset.py`

**Interfaces:**
- Consumes: `label3d`, `build_forward_path`, `render_multiframe`, `vol_scalars`, `intraday_rebound.db.read_sql/MINUTE_DB`, `intraday_rebound.universe.load_frozen_universe`, `intraday_rebound.resample.resample_ohlcv`
- Produces:
  - `iter_candidate_times(bars3: pd.DataFrame, decision_start, cutoff_from_end_bars: int) -> list[pd.Timestamp]` — 순수 함수. 3분봉에서 결정 시각 목록(10:00 이후, 마지막 `cutoff_from_end_bars` 봉 제외).
  - `build_sample(day_bars_1m: dict, entry_day, entry_dt, tp, sl) -> dict | None` — 순수 함수(DB 무관). 한 시점 → `{image:(6,64,64) float32, scalars:(2,) float32, outcome:str, realized_ret:float, stock_code, trade_date, entry_time}`. 전방경로/체결 없으면 None.
  - `build_dataset(start, end, tp, sl, sample_every_n_days=1, out_dir=...) -> dict` — DB 순회. `out_dir` 에 `images.npy`(memmap), `meta.parquet` 저장. 요약 dict 반환.
    - 라벨 TP/SL 은 **인자로 받는다**(계획 2의 워크포워드가 폴드별 학습에서 정한 값을 주입). 기본값은 스파이크 관찰용 placeholder 3%/3%.

- [ ] **Step 1: 실패 테스트 작성 (순수 함수 2개만 TDD, DB 순회는 스모크)**

`test_build_dataset.py`:

```python
import numpy as np
import pandas as pd
import pytest

from scripts.discovery.multiframe_chart_cnn.build_dataset import (
    iter_candidate_times, build_sample,
)


def _day_1m(date, start_price=100.0, n=390, drift=0.0):
    base = pd.Timestamp(f"{date[:4]}-{date[4:6]}-{date[6:]} 09:00:00")
    dts = [base + pd.Timedelta(minutes=i) for i in range(n)]
    p = start_price + drift * np.arange(n)
    return pd.DataFrame({"datetime": dts, "open": p, "high": p * 1.002,
                         "low": p * 0.998, "close": p, "volume": 100.0, "amount": p * 100})


def test_iter_candidate_times_excludes_open_hour_and_tail():
    from scripts.discovery.intraday_rebound.resample import resample_ohlcv
    bars3 = resample_ohlcv(_day_1m("20260601"), 3)
    times = iter_candidate_times(bars3, pd.Timestamp("10:00:00").time(), 20)
    assert all(t.time() >= pd.Timestamp("10:00:00").time() for t in times)
    # 마지막 20봉 제외 확인
    assert times[-1] < bars3["datetime"].iloc[-1]


def test_build_sample_produces_shapes_and_label():
    # 3거래일: 진입일 + 2일. 상승 드리프트 → tp 도달 기대
    day_bars = {
        "20260601": _day_1m("20260601", 100.0, 900, drift=0.0),   # 15분봉 60봉 확보
        "20260602": _day_1m("20260602", 100.0, 390, drift=0.05),  # 강한 상승
        "20260603": _day_1m("20260603", 120.0, 390, drift=0.0),
    }
    entry_dt = day_bars["20260601"]["datetime"].iloc[800]
    s = build_sample(day_bars, "20260601", entry_dt, tp=0.03, sl=0.03)
    assert s is not None
    assert s["image"].shape == (6, 64, 64)
    assert s["scalars"].shape == (2,)
    assert s["outcome"] in {"tp", "sl", "timeout"}
    assert s["stock_code"] is None or isinstance(s["trade_date"], str)


def test_build_sample_none_when_no_forward():
    day_bars = {"20260601": _day_1m("20260601", 100.0, 900)}
    entry_dt = day_bars["20260601"]["datetime"].iloc[-1]  # 마지막봉, 전방 없음
    s = build_sample(day_bars, "20260601", entry_dt, tp=0.03, sl=0.03)
    assert s is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd RoboTrader_template && PYTHONPATH=. python -m pytest tests/discovery/multiframe_chart_cnn/test_build_dataset.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: 구현 작성**

`build_dataset.py`:

```python
# scripts/discovery/multiframe_chart_cnn/build_dataset.py
"""데이터셋 추출: 199종목 전 거래일 전 시점 → (이미지·스칼라·라벨·메타) 캐시.

순수 조립부(iter_candidate_times/build_sample)는 DB 무관·테스트 고정.
build_dataset 만 DB를 순회한다. TP/SL 은 인자로 주입한다(계획 2 워크포워드가
폴드 학습에서 정한 값을 넣는다).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.discovery.intraday_rebound.db import MINUTE_DB, read_sql
from scripts.discovery.intraday_rebound.resample import resample_ohlcv
from scripts.discovery.intraday_rebound.universe import load_frozen_universe
from .forward_path import build_forward_path
from .label3d import label3d
from .rasterize import render_multiframe
from .scalars import vol_scalars

REGULAR_OPEN = pd.Timestamp("09:00:00").time()
REGULAR_CLOSE = pd.Timestamp("15:30:00").time()
DECISION_START = pd.Timestamp("10:00:00").time()
CACHE_DIR = Path(__file__).parent / "_cache"

_DAYS_SQL = """
SELECT DISTINCT trade_date FROM minute_candles
WHERE trade_date BETWEEN %s AND %s ORDER BY trade_date
"""
_BARS_SQL = """
SELECT stock_code, datetime, open, high, low, close, volume, amount
FROM minute_candles WHERE trade_date = %s AND stock_code = ANY(%s)
ORDER BY stock_code, datetime
"""


def iter_candidate_times(bars3: pd.DataFrame, decision_start, cutoff_from_end_bars: int):
    if bars3 is None or len(bars3) == 0:
        return []
    dt = pd.to_datetime(bars3["datetime"])
    times = dt[dt.dt.time >= decision_start]
    if cutoff_from_end_bars > 0:
        times = times.iloc[:-cutoff_from_end_bars] if len(times) > cutoff_from_end_bars else times.iloc[0:0]
    return list(times)


def build_sample(day_bars_1m: dict, entry_day: str, entry_dt, tp: float, sl: float,
                 stock_code: str | None = None):
    # 진입 시각까지의 1분봉으로 이미지/스칼라.
    entry_frame = day_bars_1m[entry_day]
    hist = entry_frame[pd.to_datetime(entry_frame["datetime"]) <= entry_dt]
    if len(hist) == 0:
        return None
    fwd = build_forward_path(day_bars_1m, entry_day, entry_dt, horizon_days=3)
    if fwd is None:
        return None
    entry_open, fh, fl, fo, fc = fwd
    outcome, realized = label3d(entry_open, fh, fl, fo, fc, tp, sl)

    image = render_multiframe(hist)
    scal = vol_scalars(resample_ohlcv(hist, 3))
    return {
        "image": image, "scalars": scal,
        "outcome": outcome, "realized_ret": realized,
        "stock_code": stock_code, "trade_date": entry_day,
        "entry_time": pd.Timestamp(entry_dt),
    }


def build_dataset(start: str, end: str, tp: float = 0.03, sl: float = 0.03,
                  sample_every_n_days: int = 1, cutoff_from_end_bars: int = 20,
                  out_dir: Path = CACHE_DIR) -> dict:
    codes = load_frozen_universe()
    days = read_sql(_DAYS_SQL, (start, end), MINUTE_DB)["trade_date"].tolist()
    # 라벨은 3거래일 전방이 필요 → 마지막 2거래일은 진입 불가(전방 절단).
    # 날짜 층화 추출: sample_every_n_days 간격의 거래일만 진입일로.
    entry_days = days[::sample_every_n_days]

    out_dir.mkdir(parents=True, exist_ok=True)
    images = []
    meta_rows = []

    # 3거래일 창을 위해 각 진입일마다 앞으로 최대 4거래일치 봉이 필요.
    day_index = {d: i for i, d in enumerate(days)}
    for d in entry_days:
        i = day_index[d]
        window = days[i:i + 3]
        if len(window) < 1:
            continue
        # 창 거래일 봉을 종목별로 로드.
        per_stock: dict[str, dict] = {code: {} for code in codes}
        for wd in window:
            raw = read_sql(_BARS_SQL, (wd, codes), MINUTE_DB)
            if raw.empty:
                continue
            raw["datetime"] = pd.to_datetime(raw["datetime"])
            t = raw["datetime"].dt.time
            raw = raw[(t >= REGULAR_OPEN) & (t <= REGULAR_CLOSE)]
            for code, g in raw.groupby("stock_code", sort=False):
                per_stock[code][wd] = g.reset_index(drop=True)

        for code in codes:
            day_bars = per_stock[code]
            if d not in day_bars:
                continue
            bars3 = resample_ohlcv(day_bars[d], 3)
            for entry_dt in iter_candidate_times(bars3, DECISION_START, cutoff_from_end_bars):
                s = build_sample(day_bars, d, entry_dt, tp, sl, stock_code=code)
                if s is None:
                    continue
                images.append(s["image"])
                meta_rows.append({k: s[k] for k in
                                  ("outcome", "realized_ret", "stock_code", "trade_date", "entry_time")})
        print(f"day {d}: samples_so_far={len(images)}")

    if not images:
        return {"n": 0}
    arr = np.stack(images).astype(np.float32)
    np.save(out_dir / "images.npy", arr)
    meta = pd.DataFrame(meta_rows)
    meta.to_parquet(out_dir / "meta.parquet", index=False)
    return {"n": len(images), "image_shape": arr.shape,
            "pct_tp": float((meta["outcome"] == "tp").mean()),
            "pct_sl": float((meta["outcome"] == "sl").mean()),
            "pct_timeout": float((meta["outcome"] == "timeout").mean())}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20260601")
    ap.add_argument("--end", default="20260607")
    ap.add_argument("--tp", type=float, default=0.03)
    ap.add_argument("--sl", type=float, default=0.03)
    ap.add_argument("--every", type=int, default=1)
    args = ap.parse_args()
    print(build_dataset(args.start, args.end, args.tp, args.sl, args.every))
```

- [ ] **Step 4: 순수함수 테스트 통과 확인**

Run: `cd RoboTrader_template && PYTHONPATH=. python -m pytest tests/discovery/multiframe_chart_cnn/test_build_dataset.py -v`
Expected: 3 passed

- [ ] **Step 5: 5거래일 실제 추출 스모크 (DB 순회)**

Run: `cd RoboTrader_template && PYTHONPATH=. python -m scripts.discovery.multiframe_chart_cnn.build_dataset --start 20260601 --end 20260607 --every 1`
Expected: `{'n': <수천>, 'image_shape': (n,6,64,64), 'pct_tp':..., 'pct_sl':..., 'pct_timeout':...}`. `_cache/images.npy` 와 `meta.parquet` 생성. pct 합 ≈ 1.0.

- [ ] **Step 6: 커밋**

```bash
git add RoboTrader_template/scripts/discovery/multiframe_chart_cnn/build_dataset.py \
        RoboTrader_template/tests/discovery/multiframe_chart_cnn/test_build_dataset.py
git commit -m "feat(mfcnn): 데이터셋 추출기(전시점 순회→이미지/스칼라/라벨 캐시) + 테스트"
```

- [ ] **Step 7: STOP — 계획 1 완료 리뷰 체크포인트**

`build_dataset` 스모크의 라벨 분포(pct_tp/sl/timeout)와 이미지 캐시 용량을 보고한다. 이 분포가 **TP/SL 실현성**(3거래일에 3%/3%가 얼마나 도달하는지)의 첫 실측이다. 계획 2(모델·워크포워드) 태스크는 이 숫자를 보고 확정한다.

---

## Self-Review (작성자 체크)

- **스펙 커버리지**: §2 이미지사양→Task 4, §2 정규화→Task 4 스케일불변 테스트, §2 변동성보조입력→Task 5, §3 라벨/청산/갭실현→Task 2, §3 TP/SL 학습구간 결정→Task 6 인자주입(값 선택은 계획 2), §2 시점/유니버스→Task 6 iter_candidate_times + load_frozen_universe, §6 리스크1 예산→Task 1, §6 리스크3 갭→Task 2. **모델(§4 A/B)·워크포워드(§4)는 계획 2**로 분리(명시).
- **플레이스홀더**: 없음. 모든 코드 스텝에 실제 코드 포함.
- **타입 일관성**: `render_multiframe`→(6,64,64), `vol_scalars`→(2,), `label3d`→(str,float), `build_forward_path`→(entry_open,fh,fl,fo,fc)|None, `build_sample`→dict|None. Task 6이 앞 4개 시그니처를 정확히 소비.
- **의존성**: 모든 재사용 심볼(read_sql/MINUTE_DB/resample_ohlcv/load_frozen_universe)은 실제 확인된 시그니처.
