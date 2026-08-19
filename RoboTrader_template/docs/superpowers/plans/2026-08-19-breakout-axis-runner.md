# 「돌파 방아쇠」 축 실행기 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사전등록 문서 5(`PREREG_BREAKOUT.md`)를 실행할 수 있도록 `run.py` 에 arm `B`/`P`/`Q`/`DB`,
크기정합+당일수익률층화 귀무 `R_B`(시드 100), 「선택 종목-일」 기준 1단계 게이트, 2단계 판정을 **추가**한다.

**Architecture:** `run.py` 에 **추가만** 한다. 문서 1이 쓰는 `ARM_RULE`·`build_cache`·`build_pools`·
`select_random`·`stage1`·`stage2` 는 **한 줄도 고치지 않는다**. 신규 경로는 별도 함수(`*_breakout`)와
별도 스테이지(`stage1b`/`stage2b`)로 두고, 로더(`load_prices`/`load_universe`/`eligible_by_date`)와
선택기(`select_top`)·백테스트 러너(`run_arm`)·순열 p(`perm_p`)는 **그대로 재사용**한다.

**Tech Stack:** Python 3.9 · pandas · numpy · psycopg2 · pytest

**Spec:** `RoboTrader_template/backtest/concept_axes/minervini/PREREG_BREAKOUT.md`

## Global Constraints

- 🔴 **문서 1 재현성**: `ARM_RULE`·`build_cache`·`build_pools`·`select_random`·`stage1`·`stage2` 를
  **수정 금지**. 시그니처·반환 형태·상수값 전부 불변.
- 🔴 **1단계는 `BookBacktester` 를 import 하지도 호출하지도 않는다** (PnL 무접근 보증).
  `stage2b` 만 지역 import 한다 — `stage2` 와 같은 방식.
- 동결 상수 (스윕 금지): `PIVOT_WIN = 25` · `RVOL_MIN = 1.5` · `S_BREAKOUT = 100` ·
  `GATE_MIN_SELECTED = 1500`. 기존 `LOOKBACK = 260` · `MAX_CANDIDATES = 10` · `EPS_ECON = 0.5` ·
  창 `W0 = "2024-03-13"` · `W1 = "2026-05-31"` 승계.
- 🔴 **테스트는 워크트리에서만 실행한다.** 라이브 트리(`D:\GIT\kis-trading-template`)에서
  pytest·스모크 실행 금지. 워크트리는 `superpowers:using-git-worktrees` 로 만든다.
- 테스트 실행: repo 루트에서
  `& "C:\Program Files (x86)\Microsoft Visual Studio\Shared\Python39_64\python.exe" -m pytest -q`
- 신규 테스트는 **DB 에 붙지 않는다** (순수 함수 + 합성 데이터만).
- 회귀 판정은 **실패 «집합»의 양방향 차분**으로. 실패 수 비교 금지.

### ⚠️ 실행자에게 미리 알리는 불일치 1건

`PREREG_BREAKOUT.md` §10-1 의 `B` 트리거 **11,330** 은 탐색 스파이크가 `i >= 26`(= 창 27봉) 가드로
낸 값이다. 사양 본문(§2)은 **「창 안 봉이 26개 이상」** = `i >= 25` 다. **사양 본문을 따른다.**
따라서 최종 산출이 11,330 과 **소폭 다를 수 있고, 그것이 정상**이다.
🔴 이 차이를 없애려고 사양을 고치지 말 것. `stage1b` 가 실제 값을 인쇄하므로 차이는 기록으로 남는다.

---

### Task 1: 문서 1 재현성 «핀» 테스트 (프로덕션 코드 변경 0)

이후 태스크가 `run.py` 를 건드릴 때 문서 1 경로가 조용히 바뀌는 것을 막는 잠금장치를 «먼저» 만든다.

**Files:**
- Create: `RoboTrader_template/tests/test_concept_axes_doc1_pin.py`

**Interfaces:**
- Consumes: 없음
- Produces: 없음 (회귀 가드 전용)

- [ ] **Step 1: 핀 테스트 작성**

```python
"""문서 1(minervini PREREG.md) 실행 경로의 «동결» 잠금.

이후 문서 5(돌파 축)를 위해 run.py 에 코드가 «추가»되는데, 그 과정에서 문서 1의
arm·캐시·시드·상수가 바뀌면 판정 완료된 결과를 재현할 수 없게 된다.
🔑 이 파일은 「추가는 허용, 변경은 금지」를 기계로 강제한다.
"""
import importlib
import inspect

import pytest

RUN = importlib.import_module(
    "backtest.concept_axes.minervini.run"
)


class TestDoc1FrozenConstants:
    def test_window_and_thresholds(self):
        assert RUN.W0 == "2024-03-13"
        assert RUN.W1 == "2026-05-31"
        assert RUN.HIST0 == "2021-01-01"
        assert RUN.LOOKBACK == 260
        assert RUN.SCORE_WINDOW == 30
        assert RUN.MAX_CANDIDATES == 10
        assert RUN.N_SEEDS == 20
        assert RUN.EPS_ECON == 0.5
        assert RUN.MIN_TRIGGER_FRAC == 0.10


class TestDoc1FrozenArms:
    def test_arm_rule_keys_exact(self):
        assert set(RUN.ARM_RULE) == {"D", "DT", "DF", "DTF", "T"}

    def test_arm_rule_arity_is_three(self):
        for name, fn in RUN.ARM_RULE.items():
            sig = inspect.signature(fn)
            assert len(sig.parameters) == 3, f"{name} arity changed"

    def test_arm_rule_truth_table(self):
        # (dry, tt, f) -> 기대 발화
        cases = [
            ((True, False, False), {"D"}),
            ((True, True, False), {"D", "DT", "T"}),
            ((True, False, True), {"D", "DF"}),
            ((True, True, True), {"D", "DT", "DF", "DTF", "T"}),
            ((False, True, False), {"T"}),
            ((False, False, False), set()),
        ]
        for args, expect in cases:
            fired = {a for a, fn in RUN.ARM_RULE.items() if fn(*args)}
            assert fired == expect, f"{args} -> {fired}, expected {expect}"


class TestDoc1FrozenSignatures:
    def test_build_cache_signature(self):
        sig = inspect.signature(RUN.build_cache)
        assert list(sig.parameters) == ["px", "elig", "rs", "fin", "params"]

    def test_build_pools_signature(self):
        sig = inspect.signature(RUN.build_pools)
        assert list(sig.parameters) == ["cache", "elig"]

    def test_select_random_signature(self):
        sig = inspect.signature(RUN.select_random)
        assert list(sig.parameters) == ["pool", "seed"]

    def test_stage1_takes_no_args(self):
        assert list(inspect.signature(RUN.stage1).parameters) == []

    def test_stage2_takes_no_args(self):
        assert list(inspect.signature(RUN.stage2).parameters) == []


class TestDoc1CacheTupleShape:
    """build_cache 의 «값 튜플 길이 5» 를 못박는다.

    build_pools 가 `(score, dry, tt, f, _close)` 로 언패킹하므로 길이가 바뀌면
    문서 1 이 즉시 깨진다. 문서 5 는 «별도» 캐시를 쓰도록 설계됐다.
    """

    def test_build_pools_unpacks_five(self):
        src = inspect.getsource(RUN.build_pools)
        assert "(score, dry, tt, f, _close)" in src
```

- [ ] **Step 2: 테스트 실패/통과 확인 (아직 코드 변경 전이므로 «통과»해야 한다)**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_doc1_pin.py -q`
Expected: **PASS** — 이 시점엔 `run.py` 가 원본이므로 전부 통과가 정상이다.
하나라도 실패하면 **내가 읽은 `run.py` 와 실제가 다르다는 뜻**이므로 멈추고 보고할 것.

- [ ] **Step 3: 커밋**

```bash
git add RoboTrader_template/tests/test_concept_axes_doc1_pin.py
git commit -m "test(concept-axes): 문서 1 실행 경로 동결 핀 — 돌파 축 추가 전 잠금"
```

---

### Task 2: 돌파 판정 순수 함수

**Files:**
- Modify: `RoboTrader_template/backtest/concept_axes/minervini/run.py` (상수 블록 끝 + `build_cache` **아래**에 추가)
- Test: `RoboTrader_template/tests/test_concept_axes_breakout.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `PIVOT_WIN: int = 25` · `RVOL_MIN: float = 1.5` · `S_BREAKOUT: int = 100` · `GATE_MIN_SELECTED: int = 1500`
  - `breakout_flags(high: np.ndarray, volume: np.ndarray, close: np.ndarray, i: int) -> tuple[bool, bool]`
    — `(ok_pivot, ok_rvol)` 반환

- [ ] **Step 1: 실패하는 테스트 작성**

```python
"""문서 5(PREREG_BREAKOUT.md) — 돌파 축 실행기."""
import importlib

import numpy as np
import pytest

RUN = importlib.import_module("backtest.concept_axes.minervini.run")


def _series(n=30, high=100.0, vol=1000.0):
    return (np.full(n, high), np.full(n, vol), np.full(n, high - 1.0))


class TestBreakoutFlags:
    def test_frozen_params(self):
        assert RUN.PIVOT_WIN == 25
        assert RUN.RVOL_MIN == 1.5
        assert RUN.S_BREAKOUT == 100
        assert RUN.GATE_MIN_SELECTED == 1500

    def test_insufficient_bars_returns_false(self):
        h, v, c = _series(30)
        # i = 24 -> base 는 [-1, 24) 가 되어 26봉 미만. 사양 §2 가드.
        assert RUN.breakout_flags(h, v, c, 24) == (False, False)

    def test_exactly_26_bars_is_allowed(self):
        h, v, c = _series(30)
        h[:25] = 100.0
        c[25] = 101.0          # 돌파
        v[:25] = 1000.0
        v[25] = 1600.0         # RVOL 1.6
        assert RUN.breakout_flags(h, v, c, 25) == (True, True)

    def test_pivot_uses_base_high_excluding_current_bar(self):
        h, v, c = _series(40)
        h[:30] = 100.0
        h[30] = 999.0          # «현재봉» 고가는 피벗에 들어가면 안 된다
        c[30] = 101.0
        v[:30] = 1000.0
        v[30] = 2000.0
        ok_p, ok_q = RUN.breakout_flags(h, v, c, 30)
        assert ok_p is True, "현재봉 high 가 피벗에 섞이면 돌파가 False 가 된다"

    def test_close_equal_to_pivot_is_not_breakout(self):
        h, v, c = _series(40)
        h[:30] = 100.0
        c[30] = 100.0          # 초과가 아니라 «같음»
        v[:30] = 1000.0
        v[30] = 2000.0
        ok_p, _ = RUN.breakout_flags(h, v, c, 30)
        assert ok_p is False

    def test_rvol_boundary_is_inclusive(self):
        h, v, c = _series(40)
        h[:30] = 100.0
        c[30] = 101.0
        v[:30] = 1000.0
        v[30] = 1500.0         # 정확히 1.5배
        _, ok_q = RUN.breakout_flags(h, v, c, 30)
        assert ok_q is True

    def test_zero_base_volume_is_false(self):
        h, v, c = _series(40)
        h[:30] = 100.0
        c[30] = 101.0
        v[:30] = 0.0
        v[30] = 5000.0
        _, ok_q = RUN.breakout_flags(h, v, c, 30)
        assert ok_q is False

    def test_flags_are_independent(self):
        """P(돌파만)·Q(거래량만) 분해가 가능해야 한다."""
        h, v, c = _series(40)
        h[:30] = 100.0
        c[30] = 101.0          # 돌파 O
        v[:30] = 1000.0
        v[30] = 1000.0         # RVOL 1.0 -> X
        assert RUN.breakout_flags(h, v, c, 30) == (True, False)
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'PIVOT_WIN'`

- [ ] **Step 3: 최소 구현 — `run.py` 에 «추가»**

`build_cache` 함수 정의가 끝난 직후(= `# 5. Arm 풀 · 선택` 주석 배너 **바로 위**)에 삽입:

```python
# ────────────────────────────────────────────────────────────────────────────
# 4b. 돌파 축 (PREREG_BREAKOUT.md 문서 5) — 문서 1 경로는 건드리지 않는다
# ────────────────────────────────────────────────────────────────────────────
PIVOT_WIN = 25                         # §2 동결 — rule_vcp_breakout.base_min_bars
RVOL_MIN = 1.5                         # §2 동결 — rule_vcp_breakout.rvol_threshold
S_BREAKOUT = 100                       # §2-2 동결 — R_B 시드 수
GATE_MIN_SELECTED = 1500               # §6 동결 — 선택 종목-일 문턱


def breakout_flags(high, volume, close, i: int) -> tuple:
    """PREREG_BREAKOUT §2 — `(ok_pivot, ok_rvol)`.

    base = `[i-25, i)` (**현재봉 제외**). 창 안 봉이 26개 미만이면 둘 다 False.
    🔑 두 조건을 «따로» 돌려주는 이유: arm `P`(돌파만)·`Q`(거래량만) 분해가 §5-3 이다.
    """
    if i < PIVOT_WIN:
        return False, False
    bh = high[i - PIVOT_WIN:i]
    bv = volume[i - PIVOT_WIN:i]
    base_vol = float(bv.mean())
    ok_pivot = bool(float(close[i]) > float(bh.max()))
    ok_rvol = bool(base_vol > 0 and float(volume[i]) / base_vol >= RVOL_MIN)
    return ok_pivot, ok_rvol
```

- [ ] **Step 4: 통과 확인 + 문서 1 핀 동시 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py RoboTrader_template/tests/test_concept_axes_doc1_pin.py -q`
Expected: 둘 다 PASS

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/backtest/concept_axes/minervini/run.py RoboTrader_template/tests/test_concept_axes_breakout.py
git commit -m "feat(concept-axes): 돌파 판정 순수 함수 breakout_flags (문서 5 §2)"
```

---

### Task 3: 돌파 축 캐시 `build_cache_breakout`

**Files:**
- Modify: `RoboTrader_template/backtest/concept_axes/minervini/run.py` (Task 2 블록 아래)
- Test: `RoboTrader_template/tests/test_concept_axes_breakout.py` (추가)

**Interfaces:**
- Consumes: `breakout_flags` · `LOOKBACK` · `SCORE_WINDOW` · `rule_volume_dryup`
- Produces:
  - `build_cache_breakout(px, elig, params) -> tuple[dict, dict]`
  - 캐시 값 튜플 **순서 동결**: `(score, ok_dry, ok_p, ok_q, day_ret, limit_up)`
    - `score: float` = 직전 30봉 평균 거래량 (현행 `score` 와 동일 정의)
    - `day_ret: float` = `close[i]/close[i-1] - 1`. 계산 불가면 `float("nan")`
    - `limit_up: bool` = `close[i]/close[i-1] >= 1.28`

- [ ] **Step 1: 실패하는 테스트 작성 (기존 테스트 파일에 «추가»)**

```python
class TestBuildCacheBreakout:
    def _px(self):
        """2종목 × 40봉 합성 프레임. DB 미접속."""
        import pandas as pd
        rows = []
        for code in ("AAA111", "BBB222"):
            for i in range(40):
                rows.append(dict(
                    stock_code=code, date=f"2024-01-{i+1:02d}",
                    open=100.0, high=100.0, low=99.0, close=99.0, volume=1000.0,
                ))
        df = pd.DataFrame(rows)
        # AAA111 의 마지막 봉만 돌파 + 거래량 폭증
        m = (df["stock_code"] == "AAA111") & (df["date"] == "2024-01-40")
        df.loc[m, "close"] = 120.0
        df.loc[m, "volume"] = 3000.0
        return df

    def test_cache_tuple_order_and_types(self):
        px = self._px()
        elig = {d: {"AAA111", "BBB222"} for d in px["date"].unique()}
        params = dict(recent_window=10, base_window=30, ratio_max=0.70)
        cache, stats = RUN.build_cache_breakout(px, elig, params)
        val = cache["AAA111"]["2024-01-40"]
        assert len(val) == 6, "캐시 튜플 길이가 바뀌면 build_pools_breakout 이 깨진다"
        score, ok_dry, ok_p, ok_q, day_ret, limit_up = val
        assert isinstance(score, float)
        assert isinstance(ok_dry, bool) and isinstance(ok_p, bool)
        assert isinstance(ok_q, bool) and isinstance(limit_up, bool)
        assert ok_p is True and ok_q is True

    def test_day_ret_is_close_over_prev_close(self):
        px = self._px()
        elig = {d: {"AAA111"} for d in px["date"].unique()}
        params = dict(recent_window=10, base_window=30, ratio_max=0.70)
        cache, _ = RUN.build_cache_breakout(px, elig, params)
        _, _, _, _, day_ret, limit_up = cache["AAA111"]["2024-01-40"]
        assert abs(day_ret - (120.0 / 99.0 - 1.0)) < 1e-9
        assert limit_up is True

    def test_ineligible_pairs_are_skipped(self):
        px = self._px()
        elig = {d: {"BBB222"} for d in px["date"].unique()}   # AAA111 부적격
        params = dict(recent_window=10, base_window=30, ratio_max=0.70)
        cache, stats = RUN.build_cache_breakout(px, elig, params)
        assert "AAA111" not in cache
        assert stats["n_eval"] == 40

    def test_stats_keys(self):
        px = self._px()
        elig = {d: {"AAA111", "BBB222"} for d in px["date"].unique()}
        params = dict(recent_window=10, base_window=30, ratio_max=0.70)
        _, stats = RUN.build_cache_breakout(px, elig, params)
        for k in ("n_eval", "n_dry", "n_p", "n_q", "n_b", "n_short_bars", "secs"):
            assert k in stats
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py::TestBuildCacheBreakout -q`
Expected: FAIL — `has no attribute 'build_cache_breakout'`

- [ ] **Step 3: 구현**

```python
def build_cache_breakout(px: pd.DataFrame, elig: dict, params: dict):
    """`{code: {date: (score, ok_dry, ok_p, ok_q, day_ret, limit_up)}}` (PREREG_BREAKOUT §2).

    🔴 문서 1 의 `build_cache` 와 «별도» 함수다. 값 튜플 길이가 달라 섞으면 즉시 깨지므로
    섞지 않는다. 창 길이·`score` 정의·적격 판정은 문서 1 과 동일하게 둔다(비교 가능성).
    """
    dry = rule_volume_dryup(recent_window=int(params["recent_window"]),
                            base_window=int(params["base_window"]),
                            ratio_max=float(params["ratio_max"]))
    cache: dict = defaultdict(dict)
    stats = dict(n_eval=0, n_dry=0, n_p=0, n_q=0, n_b=0, n_short_bars=0)
    t0 = time.perf_counter()
    done = 0
    total = px["stock_code"].nunique()
    for code, g in px.groupby("stock_code", sort=False):
        done += 1
        if done % 300 == 0:
            print(f"      ...{done}/{total} 종목 · 평가 {stats['n_eval']:,} · "
                  f"B {stats['n_b']:,} · {time.perf_counter()-t0:.0f}s", flush=True)
        g = g.reset_index(drop=True)
        dates = g["date"].to_numpy()
        closes = g["close"].to_numpy(dtype=float)
        highs = g["high"].to_numpy(dtype=float)
        vols = g["volume"].to_numpy(dtype=float)
        for i in range(len(g)):
            d = dates[i]
            if code not in elig.get(d, ()):
                continue
            stats["n_eval"] += 1
            lo = max(0, i + 1 - LOOKBACK)
            win = g.iloc[lo:i + 1]
            ok_dry = bool(getattr(dry.evaluate(win, {}), "triggered", False))
            if (i - lo + 1) < PIVOT_WIN + 1:
                stats["n_short_bars"] += 1
                ok_p = ok_q = False
            else:
                ok_p, ok_q = breakout_flags(highs, vols, closes, i)
            stats["n_dry"] += ok_dry
            stats["n_p"] += ok_p
            stats["n_q"] += ok_q
            stats["n_b"] += (ok_p and ok_q)
            if i > 0 and closes[i - 1] > 0:
                day_ret = float(closes[i] / closes[i - 1] - 1.0)
                limit_up = bool(closes[i] / closes[i - 1] >= 1.28)
            else:
                day_ret = float("nan")
                limit_up = False
            a = max(0, i + 1 - SCORE_WINDOW)
            cache[code][d] = (float(vols[a:i + 1].mean()), ok_dry, ok_p, ok_q,
                              day_ret, limit_up)
    stats["secs"] = time.perf_counter() - t0
    return dict(cache), stats
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py RoboTrader_template/tests/test_concept_axes_doc1_pin.py -q`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/backtest/concept_axes/minervini/run.py RoboTrader_template/tests/test_concept_axes_breakout.py
git commit -m "feat(concept-axes): build_cache_breakout — 돌파 축 캐시 (문서 5 §2)"
```

---

### Task 4: arm 정의와 풀 구성

**Files:**
- Modify: `RoboTrader_template/backtest/concept_axes/minervini/run.py` (Task 3 블록 아래)
- Test: `RoboTrader_template/tests/test_concept_axes_breakout.py` (추가)

**Interfaces:**
- Consumes: `build_cache_breakout` 캐시 형태
- Produces:
  - `ARM_RULE_B: dict[str, callable]` — 키 `{"D", "B", "P", "Q", "DB"}`, 각 `fn(dry, p, q) -> bool`
  - `build_pools_breakout(cache, elig) -> tuple[dict, dict, dict]`
    — `(pools, dayret, limitup)`
    - `pools: {arm: {date: [(code, score)]}}` — `"ALL"` 키에 그날 적격 전체 포함
    - `dayret: {date: {code: float}}` (NaN 은 담지 않는다)
    - `limitup: {date: {code: bool}}`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
class TestArmRuleB:
    def test_keys_exact(self):
        assert set(RUN.ARM_RULE_B) == {"D", "B", "P", "Q", "DB"}

    def test_truth_table(self):
        cases = [
            ((True, True, True), {"D", "B", "P", "Q", "DB"}),
            ((False, True, True), {"B", "P", "Q"}),
            ((True, True, False), {"D", "P"}),
            ((True, False, True), {"D", "Q"}),
            ((False, False, False), set()),
        ]
        for args, expect in cases:
            fired = {a for a, fn in RUN.ARM_RULE_B.items() if fn(*args)}
            assert fired == expect, f"{args} -> {fired}"

    def test_doc1_arm_rule_untouched(self):
        assert set(RUN.ARM_RULE) == {"D", "DT", "DF", "DTF", "T"}


class TestBuildPoolsBreakout:
    def _cache(self):
        # (score, ok_dry, ok_p, ok_q, day_ret, limit_up)
        return {
            "AAA111": {"D1": (100.0, True, True, True, 0.07, False)},
            "BBB222": {"D1": (200.0, True, False, False, -0.01, False)},
            "CCC333": {"D1": (300.0, False, True, True, 0.30, True)},
        }

    def test_pools_and_all_key(self):
        elig = {"D1": {"AAA111", "BBB222", "CCC333"}}
        pools, dayret, limitup = RUN.build_pools_breakout(self._cache(), elig)
        assert {c for c, _ in pools["ALL"]["D1"]} == {"AAA111", "BBB222", "CCC333"}
        assert {c for c, _ in pools["B"]["D1"]} == {"AAA111", "CCC333"}
        assert {c for c, _ in pools["DB"]["D1"]} == {"AAA111"}
        assert {c for c, _ in pools["D"]["D1"]} == {"AAA111", "BBB222"}

    def test_dayret_and_limitup_maps(self):
        elig = {"D1": {"AAA111", "BBB222", "CCC333"}}
        _, dayret, limitup = RUN.build_pools_breakout(self._cache(), elig)
        assert abs(dayret["D1"]["AAA111"] - 0.07) < 1e-12
        assert limitup["D1"]["CCC333"] is True

    def test_nan_dayret_is_excluded(self):
        cache = {"AAA111": {"D1": (100.0, True, True, True, float("nan"), False)}}
        elig = {"D1": {"AAA111"}}
        _, dayret, _ = RUN.build_pools_breakout(cache, elig)
        assert "AAA111" not in dayret.get("D1", {})

    def test_ineligible_excluded(self):
        elig = {"D1": {"AAA111"}}
        pools, _, _ = RUN.build_pools_breakout(self._cache(), elig)
        assert {c for c, _ in pools["ALL"]["D1"]} == {"AAA111"}
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py::TestArmRuleB -q`
Expected: FAIL — `has no attribute 'ARM_RULE_B'`

- [ ] **Step 3: 구현**

```python
ARM_RULE_B = {
    "D":  lambda dry, p, q: dry,              # 기준선 (문서 1 의 D 와 같은 정의)
    "B":  lambda dry, p, q: p and q,          # 🔴 주 검정
    "P":  lambda dry, p, q: p,                # 기술통계 — 돌파만
    "Q":  lambda dry, p, q: q,                # 기술통계 — 거래량만
    "DB": lambda dry, p, q: dry and p and q,  # 기술통계 — 「판별 보류」 사전 라벨
}


def build_pools_breakout(cache: dict, elig: dict):
    """`(pools, dayret, limitup)` — `pools["ALL"]` 은 그날 적격 «전체»(귀무 추출 풀)."""
    pools = {a: defaultdict(list) for a in list(ARM_RULE_B) + ["ALL"]}
    dayret: dict = defaultdict(dict)
    limitup: dict = defaultdict(dict)
    for code, dd in cache.items():
        for d, (score, ok_dry, ok_p, ok_q, day_ret, lim) in dd.items():
            if code not in elig.get(d, ()):
                continue
            pools["ALL"][d].append((code, score))
            limitup[d][code] = bool(lim)
            if day_ret == day_ret:      # NaN 제외
                dayret[d][code] = float(day_ret)
            for a, fn in ARM_RULE_B.items():
                if fn(ok_dry, ok_p, ok_q):
                    pools[a][d].append((code, score))
    return ({a: {d: sorted(v) for d, v in p.items() if v} for a, p in pools.items()},
            dict(dayret), dict(limitup))
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py RoboTrader_template/tests/test_concept_axes_doc1_pin.py -q`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/backtest/concept_axes/minervini/run.py RoboTrader_template/tests/test_concept_axes_breakout.py
git commit -m "feat(concept-axes): ARM_RULE_B + build_pools_breakout (문서 5 §2)"
```

---

### Task 5: 🔴 크기정합 + 당일수익률 층화 귀무 `R_B`

이 태스크가 문서 5의 **핵심**이다. 기존 `R` 이 반보수적이었던 원인 둘(크기 불일치·모멘텀 교란)을
동시에 없앤다.

**Files:**
- Modify: `RoboTrader_template/backtest/concept_axes/minervini/run.py` (Task 4 블록 아래)
- Test: `RoboTrader_template/tests/test_concept_axes_breakout.py` (추가)

**Interfaces:**
- Consumes: `select_top` · `MAX_CANDIDATES`
- Produces:
  - `select_random_matched(pool_all: dict, arm_pool: dict, dayret: dict, seed: int) -> tuple[dict, dict]`
    — `(sel, diag)`. `sel = {date: [code, ...]}` (이미 `select_top` 적용됨).
      `diag` 키: `n_days` · `n_need` · `n_drawn` · `n_sub` · `n_no_ret`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
class TestSelectRandomMatched:
    def _fixture(self, n=100, k=7):
        """1일치. 풀 n종목, arm 이 «상위 수익률» k종목을 고른 상황."""
        pool_all = {"D1": [(f"C{i:04d}", float(1000 - i)) for i in range(n)]}
        dayret = {"D1": {f"C{i:04d}": (n - i) / 1000.0 for i in range(n)}}
        arm_pool = {"D1": [(f"C{i:04d}", float(1000 - i)) for i in range(k)]}
        return pool_all, arm_pool, dayret

    def test_size_matches_arm_trigger_count(self):
        pool_all, arm_pool, dayret = self._fixture(n=100, k=7)
        sel, diag = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=0)
        # k=7 < MAX_CANDIDATES=10 이므로 절단 없이 7개
        assert len(sel["D1"]) == 7
        assert diag["n_need"] == 7

    def test_select_top_cap_applied(self):
        pool_all, arm_pool, dayret = self._fixture(n=100, k=40)
        sel, _ = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=0)
        assert len(sel["D1"]) == RUN.MAX_CANDIDATES

    def test_stratification_matches_decile_histogram(self):
        """arm 이 최상위 분위에만 있으면 R_B 도 그 분위에서만 뽑혀야 한다."""
        pool_all, arm_pool, dayret = self._fixture(n=100, k=7)
        sel, _ = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=3)
        picked = sel["D1"]
        vals = [dayret["D1"][c] for c in picked]
        # arm 7개는 전부 상위 10% 안. 뽑힌 것도 상위 10% 경계 위여야 한다.
        import numpy as np
        edge = np.quantile(list(dayret["D1"].values()), 0.9)
        assert all(v >= edge for v in vals), f"층화 실패: {vals}"

    def test_deterministic_for_same_seed(self):
        pool_all, arm_pool, dayret = self._fixture()
        a, _ = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=11)
        b, _ = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=11)
        assert a == b

    def test_different_seeds_differ(self):
        pool_all, arm_pool, dayret = self._fixture(n=200, k=15)
        a, _ = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=1)
        b, _ = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=2)
        assert a != b

    def test_arm_own_picks_are_not_excluded_from_pool(self):
        """§2-2 3단계 — arm 자신이 고른 종목을 빼면 «반대 방향»으로 편향된다."""
        pool_all = {"D1": [("X1", 10.0), ("X2", 9.0)]}
        dayret = {"D1": {"X1": 0.05, "X2": 0.05}}
        arm_pool = {"D1": [("X1", 10.0), ("X2", 9.0)]}
        sel, _ = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=0)
        assert set(sel["D1"]) == {"X1", "X2"}

    def test_substitution_counted_when_bucket_short(self):
        """한 분위에 필요한 만큼 없으면 인접 분위로 대체하고 «센다»."""
        pool_all = {"D1": [(f"C{i}", float(i)) for i in range(10)]}
        dayret = {"D1": {f"C{i}": i / 100.0 for i in range(10)}}
        # arm 이 같은 분위에서 3개를 요구하지만 그 분위엔 1개뿐인 상황을 만든다
        arm_pool = {"D1": [("C9", 9.0), ("C9", 9.0), ("C9", 9.0)]}
        sel, diag = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=0)
        assert diag["n_sub"] >= 1
        assert len(sel["D1"]) == 3

    def test_no_dayret_codes_are_counted_and_skipped(self):
        pool_all = {"D1": [("A", 1.0), ("B", 2.0), ("C", 3.0)]}
        dayret = {"D1": {"A": 0.01}}          # B, C 는 수익률 없음
        arm_pool = {"D1": [("A", 1.0)]}
        sel, diag = RUN.select_random_matched(pool_all, arm_pool, dayret, seed=0)
        assert diag["n_no_ret"] == 2
        assert sel["D1"] == ["A"]

    def test_empty_arm_day_produces_no_entry(self):
        pool_all = {"D1": [("A", 1.0)]}
        dayret = {"D1": {"A": 0.0}}
        sel, _ = RUN.select_random_matched(pool_all, {"D1": []}, dayret, seed=0)
        assert "D1" not in sel
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py::TestSelectRandomMatched -q`
Expected: FAIL — `has no attribute 'select_random_matched'`

- [ ] **Step 3: 구현**

```python
def select_random_matched(pool_all: dict, arm_pool: dict, dayret: dict, seed: int):
    """크기 정합 + 당일수익률 10분위 층화 귀무 `R_B` (PREREG_BREAKOUT §2-2).

    문서 1 의 `select_random` 과 다른 점 셋:
      ① 뽑는 «개수» 를 그날 arm 트리거 수 `k_d` 에 맞춘다 (크기 정합)
      ② 당일수익률 10분위 «도수분포» 를 arm 과 같게 맞춘다 (모멘텀 교란 제거)
      ③ 뽑은 「가짜 트리거 집합」에 `select_top` 을 태워 arm 과 같은 랭킹·절단을 받게 한다

    🔑 추출 풀에서 arm 자신의 선택분을 «빼지 않는다» — 빼면 귀무가
    「arm 이 «안» 고른 것들」이 되어 반대 방향으로 편향된다(§2-2 3단계).
    """
    rng = np.random.RandomState(seed)
    fake: dict = {}
    diag = dict(n_days=0, n_need=0, n_drawn=0, n_sub=0, n_no_ret=0)

    for d in sorted(arm_pool):
        arm_items = arm_pool.get(d) or []
        if not arm_items:
            continue
        allc = pool_all.get(d) or []
        rets = dayret.get(d, {})
        cand = [(c, s) for c, s in allc if c in rets]
        diag["n_no_ret"] += len(allc) - len(cand)
        if not cand:
            continue

        vals = np.array([rets[c] for c, _ in cand], dtype=float)
        edges = np.quantile(vals, np.arange(1, 10) / 10.0)

        def _bin(x: float) -> int:
            return int(np.searchsorted(edges, x, side="right"))

        buckets = {b: [] for b in range(10)}
        for (c, s), v in zip(cand, vals):
            buckets[_bin(v)].append((c, s))
        for b in range(10):                       # 시드 고정 셔플
            order = rng.permutation(len(buckets[b]))
            buckets[b] = [buckets[b][j] for j in order]

        need = {b: 0 for b in range(10)}
        n_need = 0
        for c, _ in arm_items:
            v = rets.get(c)
            if v is None:
                continue
            need[_bin(float(v))] += 1
            n_need += 1

        picked, shortfalls = [], []
        for b in range(10):
            take = min(need[b], len(buckets[b]))
            for _ in range(take):
                picked.append(buckets[b].pop())
            shortfalls += [b] * (need[b] - take)

        for b0 in shortfalls:                     # 가장 «가까운» 분위로 대체
            for off in range(1, 10):
                filled = False
                for bb in (b0 - off, b0 + off):
                    if 0 <= bb < 10 and buckets[bb]:
                        picked.append(buckets[bb].pop())
                        diag["n_sub"] += 1
                        filled = True
                        break
                if filled:
                    break

        diag["n_days"] += 1
        diag["n_need"] += n_need
        diag["n_drawn"] += len(picked)
        if picked:
            fake[d] = picked

    return select_top(fake), diag
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py RoboTrader_template/tests/test_concept_axes_doc1_pin.py -q`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add RoboTrader_template/backtest/concept_axes/minervini/run.py RoboTrader_template/tests/test_concept_axes_breakout.py
git commit -m "feat(concept-axes): 크기정합+층화 귀무 select_random_matched (문서 5 §2-2)"
```

---

### Task 6: 1단계 게이트 `stage1b`

**Files:**
- Modify: `RoboTrader_template/backtest/concept_axes/minervini/run.py` (`stage1` 정의 **아래**, `stage2` **위**)
- Test: `RoboTrader_template/tests/test_concept_axes_breakout.py` (추가)

**Interfaces:**
- Consumes: 앞 태스크 전부 + `load_prices` · `load_universe` · `eligible_by_date` ·
  `verify_strategy_params` · `db_fingerprint` · `git_sha` · `say` · `year_skew`
- Produces:
  - `gate_rows_breakout(pools, sels, dayret, limitup, px) -> list[dict]` (순수 함수, 테스트 대상)
  - `stage1b() -> int` (DB 접속 · 출력 담당)

- [ ] **Step 1: 실패하는 테스트 작성 — 순수 함수만 검증**

```python
class TestGateRowsBreakout:
    def test_selected_and_truncation_and_gate_flag(self):
        pools = {
            "B": {"D1": [(f"C{i}", float(i)) for i in range(30)]},
            "D": {"D1": [(f"C{i}", float(i)) for i in range(5)]},
        }
        sels = {"B": {"D1": [f"C{i}" for i in range(10)]},
                "D": {"D1": [f"C{i}" for i in range(5)]}}
        dayret = {"D1": {f"C{i}": 0.01 * i for i in range(30)}}
        limitup = {"D1": {f"C{i}": (i == 29) for i in range(30)}}
        rows = RUN.gate_rows_breakout(pools, sels, dayret, limitup)
        by = {r["arm"]: r for r in rows}
        assert by["B"]["triggers"] == 30
        assert by["B"]["selected"] == 10
        assert abs(by["B"]["keep_pct"] - 100 * 10 / 30) < 1e-9
        assert by["B"]["gate_pass"] is False        # 10 < GATE_MIN_SELECTED
        assert by["D"]["selected"] == 5

    def test_limit_up_and_median_dayret(self):
        pools = {"B": {"D1": [("A", 1.0), ("B", 2.0), ("C", 3.0)]}}
        sels = {"B": {"D1": ["A", "B", "C"]}}
        dayret = {"D1": {"A": 0.01, "B": 0.05, "C": 0.09}}
        limitup = {"D1": {"A": False, "B": False, "C": True}}
        rows = RUN.gate_rows_breakout(pools, sels, dayret, limitup)
        r = rows[0]
        assert abs(r["med_dayret"] - 0.05) < 1e-9
        assert abs(r["limitup_pct"] - 100 / 3) < 1e-6

    def test_regap_le5_uses_bar_gaps_within_code(self):
        """같은 종목의 «연속 발화» 비율. 상태형(dryup)과 사건형(돌파)을 가른다."""
        pools = {"B": {"D1": [("A", 1.0)], "D2": [("A", 1.0)], "D9": [("A", 1.0)]}}
        sels = {"B": {}}
        dayret = {d: {"A": 0.0} for d in ("D1", "D2", "D9")}
        limitup = {d: {"A": False} for d in ("D1", "D2", "D9")}
        rows = RUN.gate_rows_breakout(pools, sels, dayret, limitup,
                                      date_index={"D1": 0, "D2": 1, "D9": 8})
        r = rows[0]
        # 간격 [1, 7] -> ≤5 는 1/2
        assert abs(r["regap_le5_pct"] - 50.0) < 1e-9
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py::TestGateRowsBreakout -q`
Expected: FAIL — `has no attribute 'gate_rows_breakout'`

- [ ] **Step 3: 구현 — 순수 함수**

```python
def gate_rows_breakout(pools: dict, sels: dict, dayret: dict, limitup: dict,
                       date_index: dict = None) -> list:
    """1단계 게이트 행 (PREREG_BREAKOUT §6). **PnL 을 쓰지 않는다.**

    🔴 문턱은 「트리거 수」가 아니라 **「선택 종목-일」**이다 — 1번 문서 실측에서
    거래/트리거 비가 arm 간 10.7배 벌어져 게이트가 «없는 문제를 있다»고 말했다.
    """
    out = []
    for arm in [a for a in ARM_RULE_B if a in pools]:
        pool = pools[arm]
        trig = [(d, c) for d, v in pool.items() for c, _ in v]
        n_trig = len(trig)
        sel = sels.get(arm, {})
        n_sel = sum(len(v) for v in sel.values())
        rets = [dayret.get(d, {}).get(c) for d, c in trig]
        rets = [r for r in rets if r is not None]
        lims = [limitup.get(d, {}).get(c, False) for d, c in trig]
        by_code: dict = defaultdict(list)
        if date_index is None:
            order = {d: i for i, d in enumerate(sorted(pool))}
        else:
            order = date_index
        for d, c in trig:
            if d in order:
                by_code[c].append(order[d])
        gaps = []
        for c, idxs in by_code.items():
            idxs.sort()
            gaps += [idxs[k] - idxs[k - 1] for k in range(1, len(idxs))]
        out.append(dict(
            arm=arm,
            triggers=n_trig,
            selected=n_sel,
            keep_pct=(100.0 * n_sel / n_trig) if n_trig else float("nan"),
            codes=len(by_code),
            regap_le5_pct=(100.0 * sum(1 for g in gaps if g <= 5) / len(gaps))
                          if gaps else float("nan"),
            med_dayret=float(np.median(rets)) if rets else float("nan"),
            limitup_pct=(100.0 * sum(lims) / n_trig) if n_trig else float("nan"),
            gate_pass=bool(n_sel >= GATE_MIN_SELECTED),
        ))
    return out
```

- [ ] **Step 4: 구현 — `stage1b` (DB·출력)**

`stage1` 함수 정의가 끝난 직후에 삽입:

```python
def stage1b() -> int:
    """문서 5 1단계 게이트 — PnL 미조회. `BookBacktester` 를 import 하지 않는다."""
    conn = psycopg2.connect(**DSN)
    sha = git_sha()
    say("# 돌파 축 — 1단계 게이트 (PREREG_BREAKOUT §6, PnL 미조회)")
    say("")
    say(f"사전등록 [`PREREG_BREAKOUT.md`](PREREG_BREAKOUT.md)(동결) · 가족 등록부 "
        f"[`../REGISTRY.md`](../REGISTRY.md) **5번 문서** · 실행 커밋 **`{sha}`** · "
        f"창 **{W0} ~ {W1}**.")
    say("")
    say("🔑 `BookBacktester` 를 **import 하지도 호출하지도 않는다** — "
        "거래당 수익률이 메모리에 들어올 경로 자체가 없다.")
    say("")
    say(f"🔴 동결 파라미터: 피벗 창 **{PIVOT_WIN}봉** · RVOL **{RVOL_MIN}** · "
        f"시드 **{S_BREAKOUT}** · 게이트 문턱 선택 종목-일 **{GATE_MIN_SELECTED:,}**.")
    say("")

    rows, params = verify_strategy_params()
    for r in rows:
        say(r)
    say("")

    fp = db_fingerprint(conn)
    say("| 슬라이스 | 행 수 | 종목 수 | max |")
    say("|---|---|---|---|")
    for k, (a, b, c) in fp.items():
        say(f"| `{k}` | {a:,} | {b:,} | {c} |")
    say("")

    px = load_prices(conn)
    uni, _ = load_universe(conn)
    conn.close()
    scr = MinerviniVolumeDryupScreenerAdapter()
    elig = eligible_by_date(uni, scr)

    cache, cstats = build_cache_breakout(px, elig, params)
    pools, dayret, limitup = build_pools_breakout(cache, elig)
    sels = {a: select_top(pools[a]) for a in ARM_RULE_B if a in pools}

    say(f"적격 (code,date) **{cstats['n_eval']:,}** · dryup {cstats['n_dry']:,} · "
        f"P {cstats['n_p']:,} · Q {cstats['n_q']:,} · **B {cstats['n_b']:,}** · "
        f"봉부족 제외 {cstats['n_short_bars']:,}")
    say("")

    all_dates = sorted({d for v in pools.values() for d in v})
    order = {d: i for i, d in enumerate(all_dates)}
    grows = gate_rows_breakout(pools, sels, dayret, limitup, date_index=order)

    say("## 1. arm 별 게이트")
    say("")
    say("| arm | 트리거 | 선택 종목-일 | 잔존율 | 고유종목 | 재발화 ≤5봉 | 당일수익 중앙 | 상한가급 | 게이트 |")
    say("|---|---|---|---|---|---|---|---|---|")
    for r in grows:
        say(f"| `{r['arm']}` | {r['triggers']:,} | **{r['selected']:,}** | "
            f"{r['keep_pct']:.1f}% | {r['codes']:,} | {r['regap_le5_pct']:.1f}% | "
            f"{r['med_dayret']*100:+.2f}% | {r['limitup_pct']:.2f}% | "
            f"{'✅' if r['gate_pass'] else '🔴 판별 보류'} |")
    say("")

    for s in (0, 1):
        _rb, diag = select_random_matched(pools["ALL"], pools.get("B", {}), dayret, seed=s)
        say(f"- `R_B` 시드 {s} 진단 — 필요 {diag['n_need']:,} · 추출 {diag['n_drawn']:,} · "
            f"**층화 대체 {diag['n_sub']:,}** · 수익률 결측 제외 {diag['n_no_ret']:,}")
    say("")

    pool_days = {d: 1 for d in all_dates}
    for arm in ("B", "D"):
        if arm in pools:
            year_skew([(d, c) for d, v in pools[arm].items() for c, _ in v],
                      pool_days, f"arm {arm}")
    return 0
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py RoboTrader_template/tests/test_concept_axes_doc1_pin.py -q`
Expected: 전부 PASS

- [ ] **Step 6: 커밋**

```bash
git add RoboTrader_template/backtest/concept_axes/minervini/run.py RoboTrader_template/tests/test_concept_axes_breakout.py
git commit -m "feat(concept-axes): stage1b — 선택 종목-일 기준 1단계 게이트 (문서 5 §6)"
```

---

### Task 7: 게이트 보조 지표 4종 (§6-3 · §6-5 · §6-7 · §6-9)

Task 6 이 다루지 않은 사양 §6 항목 넷을 채운다. **전부 PnL 을 쓰지 않는다** — 가격 프레임만 본다.

**Files:**
- Modify: `RoboTrader_template/backtest/concept_axes/minervini/run.py` (`gate_rows_breakout` 아래)
- Test: `RoboTrader_template/tests/test_concept_axes_breakout.py` (추가)

**Interfaces:**
- Consumes: `pools`(Task 4) · `px` 프레임
- Produces:
  - `gate_exec_rows(pools, frames, idxmap, band_up_pct=0.03) -> list[dict]`
    — 키: `arm` · `band_ok_pct` · `band_dead_pct` · `impossible_up` · `vol5_med`
  - `gate_overlap(sels) -> dict[tuple[str, str], float]` — arm 쌍별 선택 종목-일 Jaccard

- [ ] **Step 1: 실패하는 테스트 작성**

```python
class TestGateExecRows:
    def _frames(self):
        import pandas as pd
        g = pd.DataFrame(dict(
            date=["D1", "D2", "D3", "D4", "D5", "D6", "D7"],
            open=[100.0, 104.0, 100.0, 100.0, 100.0, 100.0, 100.0],
            high=[100.0, 106.0, 101.0, 101.0, 101.0, 101.0, 140.0],
            low=[99.0, 103.0, 99.0, 99.0, 99.0, 99.0, 99.0],
            close=[100.0, 105.0, 100.0, 100.0, 100.0, 100.0, 135.0],
            volume=[1.0] * 7,
        ))
        frames = {"AAA": g}
        im = {d: i for i, d in enumerate(g["date"])}
        im["__last__"] = len(g) - 1
        return frames, {"AAA": im}

    def test_band_ok_when_next_open_within_3pct(self):
        frames, idxmap = self._frames()
        pools = {"B": {"D3": [("AAA", 1.0)]}}      # 다음봉(D4) 시가 100 vs 종가 100 -> 0%
        rows = RUN.gate_exec_rows(pools, frames, idxmap)
        assert rows[0]["band_ok_pct"] == 100.0

    def test_band_blocked_when_next_open_above_band(self):
        frames, idxmap = self._frames()
        pools = {"B": {"D1": [("AAA", 1.0)]}}      # D1 종가 100 -> D2 시가 104 = +4% > 3%
        rows = RUN.gate_exec_rows(pools, frames, idxmap)
        assert rows[0]["band_ok_pct"] == 0.0

    def test_band_dead_when_next_low_also_above_band(self):
        """다음날 «저가»조차 밴드 위 = 그날 내내 체결 불가."""
        frames, idxmap = self._frames()
        pools = {"B": {"D1": [("AAA", 1.0)]}}      # D2 저가 103 > 103.0? 경계 확인
        rows = RUN.gate_exec_rows(pools, frames, idxmap)
        assert rows[0]["band_dead_pct"] == 0.0     # 103 <= 103.0 이므로 체결 가능

    def test_impossible_up_bar_counted(self):
        """KRX 한도(+30%) 초과 = 데이터 인공물. 가드는 «하락»만 보므로 여기서 센다."""
        frames, idxmap = self._frames()
        pools = {"B": {"D7": [("AAA", 1.0)]}}      # 100 -> 135 = +35% > 31%
        rows = RUN.gate_exec_rows(pools, frames, idxmap)
        assert rows[0]["impossible_up"] == 1

    def test_vol5_median_is_finite(self):
        frames, idxmap = self._frames()
        pools = {"B": {"D1": [("AAA", 1.0)]}}
        rows = RUN.gate_exec_rows(pools, frames, idxmap)
        assert rows[0]["vol5_med"] == rows[0]["vol5_med"]   # not NaN


class TestGateOverlap:
    def test_jaccard_of_selected_pairs(self):
        sels = {
            "B": {"D1": ["A", "B"], "D2": ["C"]},
            "D": {"D1": ["B"], "D2": ["C", "E"]},
        }
        ov = RUN.gate_overlap(sels)
        # B = {(D1,A),(D1,B),(D2,C)} · D = {(D1,B),(D2,C),(D2,E)} -> 교집합 2 / 합집합 4
        assert abs(ov[("B", "D")] - 0.5) < 1e-9

    def test_identical_arms_are_one(self):
        sels = {"B": {"D1": ["A"]}, "P": {"D1": ["A"]}}
        assert abs(RUN.gate_overlap(sels)[("B", "P")] - 1.0) < 1e-9
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py::TestGateExecRows -q`
Expected: FAIL — `has no attribute 'gate_exec_rows'`

- [ ] **Step 3: 구현**

```python
def gate_exec_rows(pools: dict, frames: dict, idxmap: dict,
                   band_up_pct: float = 0.03) -> list:
    """실행 가능성·데이터 위생 지표 (PREREG_BREAKOUT §6-3·5·7). **PnL 미사용.**

    🔴 라이브는 `entry_band_up_pct`(기본 0.03) 를 넘으면 매수를 «스킵»하는데
    백테스트는 다음 봉 «시가»에 무조건 체결한다. 그 비대칭이 arm 마다 다르므로 센다.
    """
    out = []
    for arm in [a for a in ARM_RULE_B if a in pools]:
        n = ok = dead = imposs = 0
        vols5 = []
        for d, items in pools[arm].items():
            for c, _ in items:
                im = idxmap.get(c)
                g = frames.get(c)
                if im is None or g is None:
                    continue
                i = im.get(d)
                if i is None or i >= im["__last__"]:
                    continue
                n += 1
                close_t = float(g["close"].iloc[i])
                if close_t <= 0:
                    continue
                cap = close_t * (1.0 + band_up_pct)
                nxt_open = float(g["open"].iloc[i + 1])
                nxt_low = float(g["low"].iloc[i + 1])
                if nxt_open <= cap:
                    ok += 1
                elif nxt_low > cap:
                    dead += 1
                if i > 0:
                    prev = float(g["close"].iloc[i - 1])
                    if prev > 0 and close_t / prev > 1.31:
                        imposs += 1
                seg = g["close"].iloc[i + 1:i + 6].astype(float)
                if len(seg) >= 2:
                    vols5.append(float(seg.pct_change().dropna().std()))
        out.append(dict(
            arm=arm, n=n,
            band_ok_pct=(100.0 * ok / n) if n else float("nan"),
            band_dead_pct=(100.0 * dead / n) if n else float("nan"),
            impossible_up=imposs,
            vol5_med=float(np.median(vols5)) if vols5 else float("nan"),
        ))
    return out


def gate_overlap(sels: dict) -> dict:
    """arm 쌍별 «선택 종목-일» Jaccard (PREREG_BREAKOUT §6-9)."""
    setmap = {a: {(d, c) for d, v in s.items() for c in v} for a, s in sels.items()}
    arms = [a for a in ARM_RULE_B if a in setmap]
    out = {}
    for x in range(len(arms)):
        for y in range(x + 1, len(arms)):
            A, Bs = setmap[arms[x]], setmap[arms[y]]
            u = len(A | Bs)
            out[(arms[x], arms[y])] = (len(A & Bs) / u) if u else float("nan")
    return out
```

- [ ] **Step 4: `stage1b` 에 출력 연결**

Task 6 의 `stage1b` 안, `year_skew` 호출 **바로 위**에 삽입:

```python
    frames, idxmap = {}, {}
    for code, g in px.groupby("stock_code", sort=False):
        g2 = g[g["date"] >= W0]
        if len(g2) >= 2:
            g2 = g2.reset_index(drop=True)
            frames[code] = g2
            im = {d: i for i, d in enumerate(g2["date"].to_numpy())}
            im["__last__"] = len(g2) - 1
            idxmap[code] = im

    say("## 2. 실행 가능성 · 데이터 위생 (§6-3·5·7)")
    say("")
    say("| arm | 신호 | 밴드 통과 | 그날 내내 불가 | 불가능 상승봉 | 진입후 5봉 변동성(중앙) |")
    say("|---|---|---|---|---|---|")
    for r in gate_exec_rows(pools, frames, idxmap):
        say(f"| `{r['arm']}` | {r['n']:,} | {r['band_ok_pct']:.1f}% | "
            f"{r['band_dead_pct']:.1f}% | **{r['impossible_up']:,}** | "
            f"{r['vol5_med']*100:.2f}% |")
    say("")
    say("🔴 밴드 통과율이 arm 간 다르면 1번 문서 §7-9 의 「실행 효과는 arm 비교에 대칭」이 "
        "**이 문서에서는 거짓**이다(§6-3).")
    say("")
    say("## 3. arm 간 선택 겹침 (Jaccard, §6-9)")
    say("")
    for (x, y), v in gate_overlap(sels).items():
        say(f"- `{x}` ∩ `{y}` = **{v:.3f}**")
    say("")
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py RoboTrader_template/tests/test_concept_axes_doc1_pin.py -q`
Expected: 전부 PASS

- [ ] **Step 6: 커밋**

```bash
git add RoboTrader_template/backtest/concept_axes/minervini/run.py RoboTrader_template/tests/test_concept_axes_breakout.py
git commit -m "feat(concept-axes): 게이트 보조 지표 — 밴드·불가능상승봉·실현변동성·겹침 (문서 5 §6)"
```

---

### Task 8: 2단계 판정 `stage2b`

**Files:**
- Modify: `RoboTrader_template/backtest/concept_axes/minervini/run.py` (`stage2` 정의 **아래**)
- Test: `RoboTrader_template/tests/test_concept_axes_breakout.py` (추가)

**Interfaces:**
- Consumes: 앞 태스크 전부 + `run_arm` · `perm_p` · `ArmGated` · `BookBacktester`(지역 import)
- Produces:
  - `breakout_labels(B: float, D: float, r_means: list, eps: float) -> dict`
  - `stage2b() -> int`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
class TestBreakoutLabels:
    def test_n1_fail_yields_label_na(self):
        lab = RUN.breakout_labels(B=1.0, D=0.0, r_means=[0.5, 1.2, 0.8], eps=0.5)
        assert lab["label"] == "(나) 판별 불가"
        assert lab["n1"] is False

    def test_both_conditions_pass(self):
        lab = RUN.breakout_labels(B=2.0, D=0.0, r_means=[0.5, 0.9, 1.0], eps=0.5)
        assert lab["n1"] is True
        assert lab["label"] == "(가) 돌파는 정보다"

    def test_second_contrast_can_veto(self):
        """무작위 중앙(1.0)보다 0.5%p 이상 크지 않으면 (가) 가 아니다."""
        lab = RUN.breakout_labels(B=1.2, D=0.0, r_means=[0.5, 1.0, 1.1], eps=0.5)
        assert lab["n1"] is True          # 1.2 > max(1.1)
        assert lab["label"] == "(다) 크기 미달"
        assert lab["pass_vs_d"] is True
        assert lab["pass_vs_r"] is False

    def test_labels_are_mutually_exclusive(self):
        for B, D, rs in [(1.0, 0.0, [0.5, 1.2]), (2.0, 0.0, [0.5, 0.9]),
                         (1.2, 0.0, [0.5, 1.0, 1.1])]:
            lab = RUN.breakout_labels(B=B, D=D, r_means=rs, eps=0.5)
            assert lab["label"] in {"(나) 판별 불가", "(가) 돌파는 정보다", "(다) 크기 미달"}

    def test_perm_p_min_with_100_seeds(self):
        assert abs(RUN.perm_p(9.9, [0.0] * 100) - 1 / 101) < 1e-12
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py::TestBreakoutLabels -q`
Expected: FAIL — `has no attribute 'breakout_labels'`

- [ ] **Step 3: 구현 — 라벨 함수**

```python
def breakout_labels(B: float, D: float, r_means: list, eps: float) -> dict:
    """PREREG_BREAKOUT §5-2 — 라벨은 상호배타이며 위에서부터 우선한다."""
    n1 = bool(r_means) and all(B > x for x in r_means)
    med_r = float(np.median(r_means)) if r_means else float("nan")
    pass_vs_d = bool(B - D >= eps)
    pass_vs_r = bool(B - med_r >= eps)
    if not n1:
        label = "(나) 판별 불가"
    elif pass_vs_d and pass_vs_r:
        label = "(가) 돌파는 정보다"
    else:
        label = "(다) 크기 미달"
    return dict(label=label, n1=n1, med_r=med_r,
                pass_vs_d=pass_vs_d, pass_vs_r=pass_vs_r,
                p=perm_p(B, r_means))
```

- [ ] **Step 4: 구현 — `stage2b`**

```python
def stage2b() -> int:
    """문서 5 2단계 판정. 🔴 `stage1b` 가 끝난 «뒤»에만 돌린다."""
    from backtest.book_backtester import BookBacktester

    conn = psycopg2.connect(**DSN)
    sha = git_sha()
    rep("# 판정 — 「돌파 방아쇠」는 정보인가")
    rep("")
    rep(f"사전등록 [`PREREG_BREAKOUT.md`](PREREG_BREAKOUT.md) 실행 · **5번 문서** · "
        f"창 **{W0} ~ {W1}** · 실행 커밋 **`{sha}`**.")
    rep("")
    rep(f"🔴 ε = **{EPS_ECON}%p** · N1 = **`B > R_B {S_BREAKOUT}개 전부`** · "
        f"주 검정 **1개** · 귀무는 **크기정합+당일수익률 층화** `R_B` 다(§2-2).")
    rep("")
    rep("🔴 **이 축은 「원저작 복원」이 아니다** — 파라미터는 저장소 dataclass 기본값이고 "
        "해당 룰에 저장소가 붙인 라벨은 「(구) 조잡 proxy」다(§ 머리말).")
    rep("")

    rows, params = verify_strategy_params()
    px = load_prices(conn)
    uni, _ = load_universe(conn)
    conn.close()
    elig = eligible_by_date(uni, MinerviniVolumeDryupScreenerAdapter())

    cache, cstats = build_cache_breakout(px, elig, params)
    pools, dayret, _limitup = build_pools_breakout(cache, elig)
    sels = {a: select_top(pools[a]) for a in ARM_RULE_B if a in pools}

    frames, idxmap = {}, {}
    for code, g in px.groupby("stock_code", sort=False):
        g2 = g[g["date"] >= W0]
        if len(g2) >= 2:
            g2 = g2.reset_index(drop=True)
            frames[code] = g2
            im = {d: i for i, d in enumerate(g2["date"].to_numpy())}
            im["__last__"] = len(g2) - 1
            idxmap[code] = im

    cfg = dict(sl=params["sl"], tp=params["tp"], mh=params["mh"])
    res = {a: run_arm(sels[a], frames, idxmap, cfg, BookBacktester) for a in sels}

    r_means, r_stats = [], []
    for s in range(S_BREAKOUT):
        rb, _diag = select_random_matched(pools["ALL"], pools.get("B", {}), dayret, seed=s)
        st = run_arm(rb, frames, idxmap, cfg, BookBacktester)
        r_stats.append(st)
        r_means.append(st["mean"])
        if (s + 1) % 10 == 0:
            print(f"[R_B] {s+1}/{S_BREAKOUT}", flush=True)

    rep("## 1. arm 별 결과")
    rep("")
    rep("| arm | n | 거래당 평균 | 중앙 | 승률 | 폐기율 |")
    rep("|---|---|---|---|---|---|")
    for a in sels:
        r = res[a]
        rep(f"| `{a}` | {r['n']:,} | **{r['mean']:+.2f}%** | {r['med']:+.2f}% | "
            f"{r['win']:.0f}% | {r['discard']:.1f}% |")
    rep("")

    lab = breakout_labels(res["B"]["mean"], res["D"]["mean"], r_means, EPS_ECON)
    rep(f"- N1(`B` > `R_B` {S_BREAKOUT}개 전부): **{'성립' if lab['n1'] else '불성립'}** "
        f"· 순열 p = **{lab['p']:.4f}**")
    rep(f"- `B − D` = {res['B']['mean'] - res['D']['mean']:+.2f}%p "
        f"(ε={EPS_ECON}) → {'✅' if lab['pass_vs_d'] else '❌'}")
    rep(f"- `B − median(R_B)` = {res['B']['mean'] - lab['med_r']:+.2f}%p → "
        f"{'✅' if lab['pass_vs_r'] else '❌'}")
    rep(f"- **판정: {lab['label']}**")
    rep("")
    rep("⚠️ 검정력 약 70%(§7-6) — **음성 결과를 「돌파는 정보가 아니다」로 읽지 않는다.**")
    rep("")

    d_disc, b_disc = res["D"]["discard"], res["B"]["discard"]
    if d_disc == d_disc and b_disc == b_disc and max(d_disc, b_disc) >= 2 * min(d_disc, b_disc):
        rep(f"🔴 **혼합 대비 — 판별 보류 병기**: 폐기율 `D` {d_disc:.1f}% vs `B` {b_disc:.1f}% "
            f"(2배 이상, §6-2 사전 고정).")
        rep("")

    rep("## 2. 🔴 `R_B` 시드 전량 (§9 — 사후 크기 검증용)")
    rep("")
    rep("| 시드 | 거래당 평균 | n |")
    rep("|---|---|---|")
    for s, st in enumerate(r_stats):
        rep(f"| {s} | {st['mean']:+.4f}% | {st['n']:,} |")
    rep("")
    rep("🔑 1번 문서는 시드 평균을 stdout 으로만 찍어 **사후에 검정의 크기를 검증할 수 없었다.**")
    return 0
```

- [ ] **Step 5: 통과 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py RoboTrader_template/tests/test_concept_axes_doc1_pin.py -q`
Expected: 전부 PASS

- [ ] **Step 6: 커밋**

```bash
git add RoboTrader_template/backtest/concept_axes/minervini/run.py RoboTrader_template/tests/test_concept_axes_breakout.py
git commit -m "feat(concept-axes): stage2b — N1 + 이중 대조 판정 (문서 5 §5)"
```

---

### Task 9: CLI 배선 + 전체 회귀

**Files:**
- Modify: `RoboTrader_template/backtest/concept_axes/minervini/run.py` (`main()` 인자 파서)
- Test: `RoboTrader_template/tests/test_concept_axes_breakout.py` (추가)

**Interfaces:**
- Consumes: `stage1b` · `stage2b`
- Produces: `--stage1b` · `--stage2b` 플래그

- [ ] **Step 1: 실패하는 테스트 작성**

```python
class TestCliWiring:
    def test_stage_flags_exist(self):
        import inspect
        src = inspect.getsource(RUN.main)
        assert "--stage1b" in src
        assert "--stage2b" in src

    def test_doc1_flags_still_present(self):
        import inspect
        src = inspect.getsource(RUN.main)
        assert "--stage1" in src and "--stage2" in src

    def test_stage_functions_callable(self):
        assert callable(RUN.stage1b) and callable(RUN.stage2b)
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py::TestCliWiring -q`
Expected: FAIL — `--stage1b` 미존재

- [ ] **Step 3: 구현 — `main()` 에 «추가만»**

기존 `add_argument("--stage1", ...)` / `--stage2` 줄 **아래**에 추가하고,
분기 역시 기존 `if a.stage1: return stage1()` **아래**에 추가한다.
🔴 기존 두 줄은 **고치지 않는다.**

```python
    ap.add_argument("--stage1b", action="store_true",
                    help="문서 5(돌파 축) 1단계 게이트 — PnL 미조회")
    ap.add_argument("--stage2b", action="store_true",
                    help="문서 5(돌파 축) 2단계 판정")
```

```python
    if a.stage1b:
        return stage1b()
    if a.stage2b:
        return stage2b()
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest RoboTrader_template/tests/test_concept_axes_breakout.py RoboTrader_template/tests/test_concept_axes_doc1_pin.py -q`
Expected: 전부 PASS

- [ ] **Step 5: 🔴 전체 스위트 회귀 — 실패 «집합» 양방향 차분**

베이스라인 워크트리를 따로 만들어 **같은 조건**으로 양쪽을 돌린 뒤 집합을 비교한다.
실패 «수» 비교는 금지(환경 의존 실패가 있어 수는 흔들린다).

```bash
git worktree add --detach ../wt-base-b dad42f7   # 계획 작성 시점 HEAD
# 각각 repo 루트에서:
python -m pytest -q --tb=line > _base.txt 2>&1
python -m pytest -q --tb=line > _fix.txt 2>&1
grep -E "^(FAILED|ERROR) " _base.txt | sed 's/ - .*//' | sort > _b.txt
grep -E "^(FAILED|ERROR) " _fix.txt  | sed 's/ - .*//' | sort > _f.txt
comm -13 _b.txt _f.txt   # 신규 실패 — 반드시 비어야 한다
comm -23 _b.txt _f.txt   # 해소된 실패
```

Expected: **신규 실패 0**. passed 는 신규 테스트 수만큼 증가.

- [ ] **Step 6: 커밋**

```bash
git add RoboTrader_template/backtest/concept_axes/minervini/run.py RoboTrader_template/tests/test_concept_axes_breakout.py
git commit -m "feat(concept-axes): --stage1b/--stage2b CLI 배선 + 전체 회귀 확인"
```

---

## 실행 순서 (구현 완료 «후»)

🔴 **반드시 이 순서다. 뒤집으면 사전등록이 무의미해진다.**

1. `python run.py --stage1b > GATE_BREAKOUT.md` — **PnL 미조회**
2. **게이트 산출물을 읽고 커밋한다.** 여기서 파라미터·arm 을 바꾸면 §8-2 위반이다
3. 게이트 통과 arm 이 있을 때만 `python run.py --stage2b > RESULTS_BREAKOUT.md`
4. `PREREG_BREAKOUT.md` §9 실행 기록을 채운다
5. `../REGISTRY.md` 5번 문서 상태를 「판정 완료」로 갱신

⚠️ 1·3 은 **DB 에 붙는다.** 워크트리에서 돌리면 `.env` 가 없어 `TIMESCALE_*` 기본값이
레거시 DB 를 가리킬 수 있다 — `run.py` 의 `DSN` 은 하드코딩(`127.0.0.1:5433/kis_template`)이라
문제없지만, 다른 경로가 끼면 확인할 것.
