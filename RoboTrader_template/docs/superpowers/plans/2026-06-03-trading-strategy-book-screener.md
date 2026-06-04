# Book 19 『트레이딩 전략서』 일봉 스크리너 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 『트레이딩 전략서』의 HTS 공식 조건검색식 A~I 를 일봉 매수후보 스크리너 Rule 로 verbatim 코드화하고, 정본 멀티버스로 채택 여부를 검증한다.

**Architecture:** 기존 18권과 동일 — `strategies/books/trading_strategy_book/`에 `rules.py`(dataclass `Rule` 1개) + `strategy.py`(BookStrategy 래퍼) 를 두고, TDD 로 조건별 게이트를 검증한 뒤 `scripts/book_portfolio_multiverse.py`(한정자본·K·sl/tp/mh 스윕)로 일봉 백테스트한다. 진입만 충실 코드화, 청산은 드라이버 sl/tp/mh 근사.

**Tech Stack:** Python 3.8+, pandas, pytest, PostgreSQL(daily_prices), 기존 드라이버 `book_portfolio_multiverse.py` 재사용.

**Spec:** `docs/superpowers/specs/2026-06-03-trading-strategy-book-screener-design.md`

---

## File Structure

- Create `strategies/books/trading_strategy_book/__init__.py` — 패키지 docstring.
- Create `strategies/books/trading_strategy_book/rules.py` — `rule_envelope_200d_high`(조건식 A~I) + `ALL_RULES`. 단일 책임: 진입신호 평가.
- Create `strategies/books/trading_strategy_book/strategy.py` — `TradingStrategyBookStrategy(BookStrategy)` + `build_strategy()`. `_load_book` 가 import 하므로 필수.
- Create `tests/books/test_trading_strategy_book_daily.py` — 조건별 단위테스트 + no-lookahead + 로더 해석 스모크.
- Create `reports/books_research/trading_strategy_book/report.md` — 결과·채택판정.
- Modify `reports/books_research/index.md` + leaderboard — 19권째 추가.

`close`/`volume` 등 컬럼명만 사용(데이터 출처의 `date`/`datetime` 차이 무관). 모든 지표 trailing(과거~t), t+1 접근 금지.

---

## Task 1: 조건별 실패 테스트 작성 (TDD red)

**Files:**
- Test: `tests/books/test_trading_strategy_book_daily.py`

전조건 통과(all-pass) 픽스처를 만들고, 각 조건을 하나씩 무너뜨려 게이트를 검증한다. 참고: 조건 C(양봉)는 조건 I(시가대비 +3%)에 의해 함의되므로 단독 C-fail 테스트는 두지 않는다(테스트 docstring에 명시).

- [ ] **Step 1: Write the failing tests**

```python
"""『트레이딩 전략서』 (Book 19) — 일봉 조건식 A~I 단위테스트.

all-pass 픽스처에서 각 조건을 단독으로 무너뜨려 게이트를 확인한다.
조건 C(양봉)는 조건 I(close>=open*1.03)에 함의되므로 단독 C-fail 케이스는 없음.
모든 평가는 df 마지막 행(t)만 사용 — no-lookahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


N = 210  # 최소봉수(high_window 200 + 여유) 충족


def _arrays():
    """all-pass 기본 배열 (210봉). 마지막 봉이 조건식 A~I 전부 충족하는 돌파봉."""
    close = np.full(N, 1000.0)
    open_ = np.full(N, 1000.0)
    high = np.full(N, 1000.0)
    low = np.full(N, 995.0)
    volume = np.full(N, 6_000_000.0)
    # 마지막 봉(t = index N-1) = 200일 신고가 돌파 + 양봉 + 거래량 증가
    close[-1] = 1300.0     # 직전 200봉 종가 최고 (나머지 1000)
    open_[-1] = 1010.0     # 양봉, 갭<7%(1010<1000*1.07=1070), 시가대비 close +28%
    high[-1] = 1300.0      # 종가=고가
    low[-1] = 1005.0       # 이등분선=(1300+1005)/2=1152.5 < close
    volume[-1] = 8_000_000.0  # vol_t >= vol_prev
    return open_, high, low, close, volume


def _make_df(open_, high, low, close, volume):
    n = len(close)
    dates = pd.date_range("2023-01-02", periods=n, freq="B")
    return pd.DataFrame({
        "datetime": dates,
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    })


def _rule():
    from strategies.books.trading_strategy_book.rules import rule_envelope_200d_high
    return rule_envelope_200d_high()


def _eval(open_, high, low, close, volume):
    return _rule().evaluate(_make_df(open_, high, low, close, volume), {})


def test_all_pass_triggers():
    res = _eval(*_arrays())
    assert res.triggered is True
    assert res.side == "buy"


def test_A_not_200d_high_blocks():
    o, h, l, c, v = _arrays()
    c[50] = 1400.0  # 과거 종가가 더 높음 → t 가 200일 신고가 아님
    assert _eval(o, h, l, c, v).triggered is False


def test_B_below_envelope_blocks():
    o, h, l, c, v = _arrays()
    c[-1] = 1100.0   # 여전히 200일 신고가지만 Envelope 상단(~1111) 미달
    h[-1] = 1100.0
    o[-1] = 1000.0   # I 통과(1100>=1030), C 통과
    assert _eval(o, h, l, c, v).triggered is False


def test_D_volume_below_prev_blocks():
    o, h, l, c, v = _arrays()
    v[-1] = 5_000_000.0  # vol_t < vol_prev(6e6)
    assert _eval(o, h, l, c, v).triggered is False


def test_E_close_below_bisector_blocks():
    o, h, l, c, v = _arrays()
    h[-1] = 1700.0  # 윗꼬리 김 → 이등분선=(1700+1005)/2=1352.5 > close(1300)
    assert _eval(o, h, l, c, v).triggered is False


def test_F_low_trading_value_blocks():
    o, h, l, c, v = _arrays()
    v[:] = 4_000_000.0   # close*vol≈4e9 → 4000백만 < 5000
    v[-1] = 8_000_000.0  # D 는 통과 유지
    assert _eval(o, h, l, c, v).triggered is False


def test_G_gap_up_excluded():
    o, h, l, c, v = _arrays()
    o[-1] = 1100.0  # 시가 >= 전일종가*1.07(1070) → 갭상승 제외. I 는 1300>=1133 통과
    assert _eval(o, h, l, c, v).triggered is False


def test_H_prior_surge_excluded():
    o, h, l, c, v = _arrays()
    c[-2] = 1200.0  # 어제 종가 >= 그제(1000)*1.10 → 직전 급등 제외
    assert _eval(o, h, l, c, v).triggered is False


def test_I_intraday_gain_below_3pct_blocks():
    o, h, l, c, v = _arrays()
    o[-1] = 1290.0  # close(1300) < open*1.03(1328.7) → I 실패. C(1290<1300)는 통과
    assert _eval(o, h, l, c, v).triggered is False


def test_no_lookahead_future_bars_irrelevant():
    """t 시점 트리거는 이후 봉과 무관 — df 를 t 까지 자른 결과가 동일."""
    o, h, l, c, v = _arrays()
    df_full = _make_df(o, h, l, c, v)
    res_full = _rule().evaluate(df_full, {})
    # 이후 봉(폭락) 추가 후 t 까지 슬라이스 → 동일 결과
    extra = _make_df(
        np.full(5, 500.0), np.full(5, 500.0), np.full(5, 490.0),
        np.full(5, 500.0), np.full(5, 1_000.0),
    )
    df_more = pd.concat([df_full, extra], ignore_index=True)
    res_sliced = _rule().evaluate(df_more.iloc[: len(df_full)], {})
    assert res_full.triggered == res_sliced.triggered is True


def test_insufficient_bars_no_trigger():
    o, h, l, c, v = _arrays()
    df = _make_df(o, h, l, c, v).iloc[-50:]  # 200봉 미만
    assert _rule().evaluate(df, {}).triggered is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/books/test_trading_strategy_book_daily.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategies.books.trading_strategy_book'`

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/books/test_trading_strategy_book_daily.py
git commit -m "test(book19): 트레이딩 전략서 조건식 A~I 일봉 스크리너 실패 테스트"
```
> 주의: 커밋은 사장님 승인 후에만. 승인 전이면 이 step 은 보류하고 다음 Task 로 진행(18권 관례).

---

## Task 2: rules.py 구현 (TDD green)

**Files:**
- Create: `strategies/books/trading_strategy_book/__init__.py`
- Create: `strategies/books/trading_strategy_book/rules.py`

- [ ] **Step 1: Write `__init__.py`**

```python
"""『트레이딩 전략서』 (Book 19) — 일봉 매수후보 스크리너.

이북 부재 → 사장님 정리 노트의 HTS 공식 조건검색식 A~I 를 verbatim 코드화.
분봉(3/5분) 눌림목 실행층(이등분선/가격박스/볼린저)은 미정의 임계값 다수 + 분봉단타
전멸 전례로 범위 외(보류). 상세: docs/superpowers/specs/2026-06-03-trading-strategy-book-screener-design.md
"""
```

- [ ] **Step 2: Write `rules.py`**

```python
"""『트레이딩 전략서』 (Book 19) — 일봉 조건식 A~I 매수후보 스크리너.

평가 시점 t = df 마지막 행(0봉). 진입은 드라이버가 t+1 시가(entry_mechanism="market").
t+1 데이터 접근 금지. 모든 지표 trailing(과거~t). 데이터 컬럼: open, high, low, close, volume.

조건식: A and B and C and D and E and F and (not G) and (not H) and I
  A 200일 종가신고가      : close[t] >= max(close[t-199..t])
  B Envelope(10,10) 돌파  : close[t] >= SMA(close,env_period)[t] * (1+env_pct)
  C 양봉                  : open[t] < close[t]
  D 거래량 전일대비 100%+ : volume[t] >= volume[t-1] * vol_ratio  (전일 동시간 일봉 프록시)
  E 종가 > 이등분선       : close[t] > (high[t]+low[t])/2
  F 5일 거래대금 50억+    : mean(close*volume [t-5..t-1]) / 1e6 >= min_value_mil  (금일 제외)
  G 갭상승(제외)          : open[t] >= close[t-1] * (1+gap_excl)
  H 직전급등(제외)        : close[t-1] >= close[t-2] * (1+prior_surge_excl)
  I 당일 시가대비 +3%     : close[t] >= open[t] * (1+intraday_gain)

거래대금(F): 일봉 데이터에 별도 거래대금 컬럼이 없어 close*volume(원) → /1e6(백만) 환산.
필드 기본값 = 책 원문 verbatim. 멀티버스 그리드 스윕 노출용이나 채택판정은 기본값 기준.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import pandas as pd

from strategies.books._base_book_strategy import Rule, RuleResult


@dataclass
class rule_envelope_200d_high(Rule):
    name: str = "envelope_200d_high"
    high_window: int = 200       # A: 200일 종가신고가 룩백
    env_period: int = 10         # B: Envelope 이동평균 기간
    env_pct: float = 0.10        # B: Envelope 상단 % (10%)
    vol_ratio: float = 1.0       # D: 전일 거래량 대비 배수(100%)
    value_window: int = 5        # F: 거래대금 평균 기간
    min_value_mil: float = 5000.0  # F: 5일 평균 거래대금 하한(백만원=50억)
    gap_excl: float = 0.07       # G: 갭상승 제외 임계(7%)
    prior_surge_excl: float = 0.10  # H: 직전봉 급등 제외 임계(10%)
    intraday_gain: float = 0.03  # I: 당일 시가대비 종가 상승 하한(3%)

    def evaluate(self, df: pd.DataFrame, ctx: Dict[str, Any]) -> RuleResult:
        need = max(self.high_window, self.env_period, self.value_window) + 2
        if df is None or len(df) < need:
            return RuleResult(triggered=False)

        o = df["open"].astype(float)
        h = df["high"].astype(float)
        l = df["low"].astype(float)
        c = df["close"].astype(float)
        v = df["volume"].astype(float)

        close_t = float(c.iloc[-1]); open_t = float(o.iloc[-1])
        high_t = float(h.iloc[-1]); low_t = float(l.iloc[-1])
        vol_t = float(v.iloc[-1]); vol_prev = float(v.iloc[-2])
        close_prev = float(c.iloc[-2]); close_prev2 = float(c.iloc[-3])

        # A. 200일 종가 신고가 (close_t == 직전 high_window 봉 중 최고종가)
        window_max = float(c.iloc[-self.high_window:].max())
        if close_t < window_max:
            return RuleResult(triggered=False)

        # B. Envelope 상단 돌파
        sma = float(c.iloc[-self.env_period:].mean())
        if not (sma > 0 and close_t >= sma * (1.0 + self.env_pct)):
            return RuleResult(triggered=False)

        # C. 양봉
        if not (open_t < close_t):
            return RuleResult(triggered=False)

        # D. 거래량 전일대비 100% 이상
        if not (vol_t >= vol_prev * self.vol_ratio):
            return RuleResult(triggered=False)

        # E. 종가 > 이등분선
        if not (close_t > (high_t + low_t) / 2.0):
            return RuleResult(triggered=False)

        # F. 5일 평균 거래대금(금일 제외) >= min_value_mil(백만)
        tv_prev = (c * v).iloc[-(self.value_window + 1):-1]  # t-window .. t-1
        if len(tv_prev) < self.value_window:
            return RuleResult(triggered=False)
        avg_value_mil = float(tv_prev.mean()) / 1e6
        if not (avg_value_mil >= self.min_value_mil):
            return RuleResult(triggered=False)

        # G(제외). 당일 시가 갭상승 >= gap_excl
        if close_prev > 0 and open_t >= close_prev * (1.0 + self.gap_excl):
            return RuleResult(triggered=False)

        # H(제외). 직전봉(어제) 종가가 그제 대비 급등 >= prior_surge_excl
        if close_prev2 > 0 and close_prev >= close_prev2 * (1.0 + self.prior_surge_excl):
            return RuleResult(triggered=False)

        # I. 당일 시가대비 종가 +intraday_gain 이상
        if not (open_t > 0 and close_t >= open_t * (1.0 + self.intraday_gain)):
            return RuleResult(triggered=False)

        return RuleResult(
            triggered=True, side="buy", confidence=70.0,
            reasons=[
                f"envelope_200d_high close={close_t:.0f} >= env_upper={sma * (1 + self.env_pct):.0f} "
                f"200d_high vol>=prev value={avg_value_mil:.0f}M gain={close_t / open_t - 1:.1%}"
            ],
            metadata={"sma": sma, "avg_value_mil": avg_value_mil},
        )


# 책 전체 일봉 규칙
ALL_RULES = [rule_envelope_200d_high]
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/books/test_trading_strategy_book_daily.py -q`
Expected: PASS (11 passed)

- [ ] **Step 4: Commit**

```bash
git add strategies/books/trading_strategy_book/__init__.py strategies/books/trading_strategy_book/rules.py
git commit -m "feat(book19): 트레이딩 전략서 조건식 A~I 일봉 스크리너 룰"
```
> 커밋은 사장님 승인 후. 미승인 시 보류.

---

## Task 3: strategy.py 래퍼 + 드라이버 해석 스모크 테스트

**Files:**
- Create: `strategies/books/trading_strategy_book/strategy.py`
- Test: `tests/books/test_trading_strategy_book_daily.py` (테스트 1건 추가)

`scripts/book_param_multiverse._load_book` 는 `strategies.books.<book>.strategy`(또는 `strategy_daily`) 모듈 import 를 요구한다. 이게 없으면 멀티버스 드라이버가 ModuleNotFoundError 로 실패하므로 반드시 생성한다.

- [ ] **Step 1: Write the failing smoke test (append to test file)**

```python
def test_driver_resolves_book_and_rule():
    """멀티버스 드라이버가 책/룰을 해석할 수 있어야 한다(_load_book + _resolve_rule_cls)."""
    from scripts.book_param_multiverse import _load_book, _resolve_rule_cls, _rule_defaults
    _strat_mod, rules_mod = _load_book("trading_strategy_book")
    cls = _resolve_rule_cls(rules_mod, "envelope_200d_high")
    assert cls().name == "envelope_200d_high"
    # 클래스명(rule_ 접두) 입력도 허용
    assert _resolve_rule_cls(rules_mod, "rule_envelope_200d_high").__name__ == "rule_envelope_200d_high"
    # 기본값(책 원문) 노출 확인
    d = _rule_defaults(cls)
    assert d["high_window"] == 200 and d["env_pct"] == 0.10 and d["intraday_gain"] == 0.03
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/books/test_trading_strategy_book_daily.py::test_driver_resolves_book_and_rule -q`
Expected: FAIL — `ModuleNotFoundError: ...trading_strategy_book.strategy`

- [ ] **Step 3: Write `strategy.py`**

```python
"""『트레이딩 전략서』 (Book 19) — 일봉 매수후보 스크리너 전략 래퍼.

다른 한국 책 일봉 전략(dino_surge / haru_silijeon_daily)과 동일 구조.
진입만 충실 코드화; 청산은 멀티버스 드라이버의 sl/tp/mh 가 담당.
"""

from __future__ import annotations

from typing import List, Optional

from strategies.books._base_book_strategy import BookStrategy
from strategies.books.trading_strategy_book.rules import ALL_RULES


BOOK_META = {
    "id": "trading_strategy_book",
    "name": "트레이딩 전략서 (일봉 조건식 A~I 스크리너)",
    "category": "high_breakout_kr",
    "data_granularity": "daily",
}


class TradingStrategyBookStrategy(BookStrategy):
    name = "TradingStrategyBookStrategy"
    version = "1.0.0"
    description = "트레이딩 전략서 — 200일 신고가 + Envelope 돌파 일봉 스크리너(조건식 A~I)"
    author = "kis-template"
    holding_period = "swing"


def build_strategy(
    mode: str = "single",
    target_rule: Optional[str] = None,
    or_members: Optional[List[str]] = None,
) -> TradingStrategyBookStrategy:
    return TradingStrategyBookStrategy(
        rules=[cls() for cls in ALL_RULES],
        mode=mode,
        target_rule=target_rule,
        or_members=or_members,
    )
```

- [ ] **Step 4: Run the smoke test (and full file) to verify pass**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/books/test_trading_strategy_book_daily.py -q`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add strategies/books/trading_strategy_book/strategy.py tests/books/test_trading_strategy_book_daily.py
git commit -m "feat(book19): strategy 래퍼 + 드라이버 해석 스모크 테스트"
```
> 커밋은 사장님 승인 후. 미승인 시 보류.

---

## Task 4: 정본 멀티버스 백테스트 (전구간 + 3국면)

**Files:** 없음(실행만). 출력: `D:\tmp\multiverse\book19_*`

먼저 데이터 가용 최신일과 국면 달력창을 확정한다(추측 금지).

- [ ] **Step 1: 데이터 최신일 + 국면 달력창 확인**

Run (최신 일봉일):
```bash
cd /d/GIT/kis-trading-template/RoboTrader_template && python -c "from db.connection import DatabaseConnection;\nimport sys;\nc=DatabaseConnection.get_connection().__enter__();cur=c.cursor();cur.execute('SELECT MIN(date), MAX(date) FROM daily_prices');print(cur.fetchone())"
```
Expected: `(date(2021,...), date(2026,...))` — 전구간 `--start`/`--end` 에 사용.

국면 달력창은 기존 책 검증과 동일 라벨을 재사용한다:
Run: `grep -rn "2022-01-01\|BEAR\|BULL\|SIDE" scripts/regime_split_*.py` (또는 `reports/books_research/_REtest_portfolio_daily.md`)
→ 직전 책들이 쓴 BULL / BEAR(2022) / SIDE 의 정확한 `start~end` 를 그대로 사용. (없으면 BEAR=2022-01-01~2022-12-31, BULL=2023-01-01~2024-12-31, SIDE=2021-01-01~2021-12-31 기본 사용하고 report 에 출처 명기.)

- [ ] **Step 2: 전구간 멀티버스 실행 (백그라운드)**

Run (run_in_background=true):
```bash
cd /d/GIT/kis-trading-template/RoboTrader_template && python scripts/book_portfolio_multiverse.py \
  --book trading_strategy_book --rule envelope_200d_high --granularity daily \
  --start 2021-01-01 --end <MAX_DATE> \
  --universe top_volume:50 --K-list 3 5 10 \
  --max-per-stock 3000000 --initial-capital 10000000 \
  --exit-grid '{"sl":[0.03,0.05],"tp":[0.03,0.05,0.10],"mh":[1,2,3,5]}' \
  --workers 4 --out D:\tmp\multiverse\book19_full
```
Expected: `<out>/book_portfolio_trading_strategy_book_envelope_200d_high.tsv` 생성 + 콘솔 top-K + best vs baseline. **신호 n(거래수) 반드시 기록** — 희소하면 그 자체가 결론.

- [ ] **Step 3: 3국면 멀티버스 실행 (각 백그라운드)**

BULL/BEAR/SIDE 각각 Step 1 의 날짜로 `--start/--end` 만 바꿔 동일 커맨드 실행, `--out D:\tmp\multiverse\book19_bull|bear|side`.

- [ ] **Step 4: 결과 수집**

각 `.tsv` 의 best 행(sharpe desc→pnl desc), 거래수, K별 메트릭, baseline 대비를 표로 정리. (커밋 없음 — 산출물은 D:\tmp.)

---

## Task 5: report.md + index/leaderboard 갱신

**Files:**
- Create: `reports/books_research/trading_strategy_book/report.md`
- Modify: `reports/books_research/index.md`
- Modify: leaderboard 파일(index.md 내 leaderboard 절 또는 `reports/books_research/SUMMARY_*` — 기존 위치 확인 후 동일 위치)

- [ ] **Step 1: report.md 작성**

다음 절 포함: ① 책/노트 출처(이북부재·사장님노트) ② 코드화 범위(조건식 A~I 진입만, 분봉 실행층 보류 사유) ③ 조건식 A~I 매핑표(spec §2 복사) ④ 백테스트 결과(전구간+3국면, K별, 거래수) ⑤ **채택 판정**(Sharpe≳0.6·BEAR 비파국·강건성 / 신호 희소 시 "표본부족·부적격") ⑥ 미코드화 사유(한달내+100%·장중+20%·상한가다음날·청산 이등분선 근사한계) ⑦ leaderboard 위치.

- [ ] **Step 2: index.md 에 19권째 행 추가**

기존 책 행 포맷을 그대로 따라 `trading_strategy_book` 행 추가(카테고리 high_breakout_kr, best Sharpe/PnL, 판정).

- [ ] **Step 3: leaderboard 갱신**

기존 leaderboard 표에 best 룰 1행 추가(Elder 1.22 … 순위 안 어디에).

- [ ] **Step 4: 회귀 테스트 확인**

Run: `cd /d/GIT/kis-trading-template/RoboTrader_template && python -m pytest tests/books/ -q`
Expected: 전부 PASS (신규 12 + 기존 dino 등 무영향).

- [ ] **Step 5: Commit (승인 후)**

```bash
git add reports/books_research/trading_strategy_book/report.md reports/books_research/index.md
git commit -m "research(book19): 트레이딩 전략서 일봉 스크리너 백테스트 + 채택판정"
```
> **git 커밋·push 는 사장님 승인 후에만.** 18권 관례.

---

## Task 6: 최종 검증

- [ ] **Step 1: 전체 산출물 점검**

- `python -m py_compile strategies/books/trading_strategy_book/rules.py strategies/books/trading_strategy_book/strategy.py` → OK
- `python -m pytest tests/books/test_trading_strategy_book_daily.py -q` → 12 passed
- report/index/leaderboard 갱신 확인.
- 채택 판정이 증거(거래수·Sharpe·국면)와 일치하는지 verifier 관점 재확인(억지 채택 금지).

- [ ] **Step 2: 사장님 보고**

결과 요약 + 채택/부적격 판정 + 커밋 승인 요청.

---

## Self-Review (작성자 점검 결과)

1. **Spec coverage**: §1 산출물→Task1~3·5, §2 조건식 A~I→Task2(코드)+Task1(테스트), §2.1 범위제외→Task5 report ⑥, §3 청산 근사→Task4 exit-grid + report, §4 백테스트→Task4, §5 채택기준→Task5·6, §6 워크플로→전체, §7 R1(거래대금 컬럼)→Task2 F 구현 close*volume 확정, R2 희소성→Task4 Step2·Task5, R3 청산한계→report ⑥, R4 달력국면→Task4 Step1. 누락 없음.
2. **Placeholder scan**: 코드 step 은 전부 완전 코드. Task4 의 `<MAX_DATE>`·국면 날짜는 "데이터에서 조회"라는 구체 액션(Step1)으로 해소 — placeholder 아님.
3. **Type consistency**: 룰 클래스 `rule_envelope_200d_high`, `.name="envelope_200d_high"`, 필드명(high_window/env_period/env_pct/vol_ratio/value_window/min_value_mil/gap_excl/prior_surge_excl/intraday_gain) 이 rules.py·테스트·스모크에서 일관. `ALL_RULES`·`build_strategy`·`RuleResult(triggered/side/confidence/reasons/metadata)` 베이스와 일치.
